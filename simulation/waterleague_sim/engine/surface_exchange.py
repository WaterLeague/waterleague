"""유입부별 가용 체적과 보존적 지표 교환. 수평 운동량을 임의로 생성하지 않음."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface import SurfaceSession


class ExchangeSurfaceSession(SurfaceSession):
    def __init__(self, model, directory):
        super().__init__(model['surface'], directory)
        self.engine['exchangeAdapterSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.port_specs = model['ports']
        self.port_indices = {}
        self.exchange_net = 0.
        occupied = set()
        require(isinstance(self.port_specs, list) and 0 < len(self.port_specs) <= 10_000,
                'EXCHANGE_PORTS_REQUIRED')
        for row in self.port_specs:
            cells = row.get('surfaceTriangles')
            identifier, crest = row.get('id'), row.get('crestM')
            require(isinstance(identifier, str) and identifier and identifier not in self.port_indices
                    and isinstance(cells, list) and cells and all(type(i) is int
                        and 0 <= i < len(self.domain.areas) for i in cells)
                    and len(set(cells)) == len(cells) and not occupied.intersection(cells),
                    'EXCHANGE_PORT_REGION_INVALID')
            require(type(crest) in (int, float) and math.isfinite(crest) and row.get('evidence'),
                    'EXCHANGE_PORT_REFERENCE_REQUIRED')
            indices = self.np.asarray(cells, dtype=int)
            require(self.np.max(self.domain.quantities['elevation'].centroid_values[indices]) <= crest + 1e-7,
                    'EXCHANGE_CREST_BELOW_REGION')
            occupied.update(cells)
            self.port_indices[identifier] = indices
        (self.directory / 'exchange-ports.json').write_text(json.dumps(self.port_specs, allow_nan=False) + '\n')
        self.domain.set_store(False)
        self.domain.initialise_storage()
        self.last_frame_time = -1.
        self.store_frame()

    def _available(self, row):
        cells = self.port_indices[row['id']]
        z = self.domain.quantities['elevation'].centroid_values[cells]
        stage = self.domain.quantities['stage'].centroid_values[cells]
        return self.np.maximum(0., stage - self.np.maximum(z, row['crestM']))

    def port_state(self):
        require(not self.finished, 'SURFACE_SESSION_FINISHED')
        np, domain = self.np, self.domain
        ports = {}
        for row in self.port_specs:
            cells = self.port_indices[row['id']]
            area = float(np.sum(domain.areas[cells]))
            volume = float(np.dot(self._available(row), domain.areas[cells]))
            ports[row['id']] = {'availableM3': volume, 'regionAreaM2': area,
                'headM': row['crestM'] + volume / area}
        stage = domain.quantities['stage'].centroid_values
        depth = stage - domain.quantities['elevation'].centroid_values
        require(np.all(np.isfinite(depth)) and np.min(depth) >= -1e-10, 'SURFACE_NONPHYSICAL_RESULT')
        storage = float(np.dot(depth, domain.areas))
        boundary = float(domain.get_boundary_flux_integral())
        source = float(domain.get_fractional_step_volume_integral())
        return {'timeSeconds': float(domain.get_time()), 'ports': ports, 'storageM3': storage,
                'boundaryNetInflowM3': boundary, 'sourceNetInflowM3': source,
                'exchangeNetInflowM3': self.exchange_net, 'externalSourceNetInflowM3': source - self.exchange_net,
                'balanceResidualM3': self.initial_volume + source + boundary - storage, **self.loss_ledger()}

    def apply_exchange(self, transfers):
        require(not self.finished and isinstance(transfers, dict)
                and set(transfers) == set(self.port_indices), 'EXCHANGE_TRANSFERS_INVALID')
        np, domain = self.np, self.domain
        changes = []
        # 모든 유입부를 먼저 검증하여 잘못된 한 건 때문에 일부만 적용하지 않는다.
        for row in self.port_specs:
            volume = transfers[row['id']]
            require(type(volume) in (int, float) and math.isfinite(volume), 'EXCHANGE_VOLUME_INVALID')
            cells = self.port_indices[row['id']]
            areas = domain.areas[cells]
            available = self._available(row)
            capacity = float(np.dot(available, areas))
            require(volume >= -capacity, 'EXCHANGE_SURFACE_OVERDRAW')
            delta = (np.full(len(cells), volume / float(np.sum(areas))) if volume >= 0
                     else available * (volume / capacity))
            changes.append((row['id'], cells, delta, volume))
        records = []
        for identifier, cells, delta, volume in changes:
            stage = domain.quantities['stage'].centroid_values
            z = domain.quantities['elevation'].centroid_values
            old_depth = stage[cells] - z[cells]
            old_stage = stage[cells].copy()
            stage[cells] += delta
            if volume < 0:
                ratio = np.divide(stage[cells] - z[cells], old_depth,
                                  out=np.ones_like(old_depth), where=old_depth > 0)
                for name in ('xmomentum', 'ymomentum'):
                    domain.quantities[name].centroid_values[cells] *= ratio
            actual = float(np.dot(stage[cells] - old_stage, domain.areas[cells]))
            require(math.isclose(actual, volume, abs_tol=1e-9, rel_tol=1e-10),
                    'EXCHANGE_VOLUME_ROUNDOFF_EXCEEDED')
            domain.fractional_step_volume_integral += volume
            self.exchange_net += volume
            records.append({'port': identifier, 'requestedM3': volume, 'appliedM3': actual,
                            'roundoffM3': actual - volume})
        if self.metrics is not None:
            self.metrics.reset_at_instant()
        if self.quality is not None:
            self.quality.observe(float(domain.get_time()))
        with (self.directory / 'surface-exchange.jsonl').open('a') as stream:
            stream.write(json.dumps({'timeSeconds': domain.get_time(), 'transfers': records},
                                    allow_nan=False) + '\n')
        return {'transfers': records, 'state': self.port_state()}

    def advance_exchange(self, milliseconds):
        require(not self.finished and type(milliseconds) is int and 1 <= milliseconds <= 60_000,
                'EXCHANGE_STEP_INVALID')
        duration = milliseconds / 1000
        target = self.domain.get_time() + duration
        self._evolve_until(target)
        require(math.isclose(self.domain.get_time(), target, abs_tol=1e-8, rel_tol=0),
                'EXCHANGE_SURFACE_TIME_MISMATCH')
        return self.port_state()

    def store_frame(self):
        now = float(self.domain.get_time())
        if now > self.last_frame_time:
            # 표시 재구성의 보호 연산이 실제 중심 상태를 바꾸지 않도록 원 상태를 유지한다.
            quantities = [self.domain.quantities[name] for name in ('stage', 'xmomentum', 'ymomentum')]
            saved = [q.centroid_values.copy() for q in quantities]
            self.domain.distribute_to_vertices_and_edges()
            for quantity, values in zip(quantities, saved):
                quantity.centroid_values[:] = values
            self.domain.store_timestep()
            self.last_frame_time = now
        return {'timeSeconds': now}

    def finish(self):
        final = self.port_state()
        self.store_frame()
        result = super().finish()
        result.update({'exchange': final, 'portHeadMethod': 'AVAILABLE_VOLUME_OVER_REGION_AREA_ABOVE_CREST',
                       'momentumMethod': 'ZERO_HORIZONTAL_MOMENTUM_ADDITION_PROPORTIONAL_WITHDRAWAL'})
        (self.directory / 'surface-result.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return result
