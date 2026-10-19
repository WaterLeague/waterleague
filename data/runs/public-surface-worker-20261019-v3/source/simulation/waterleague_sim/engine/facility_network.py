"""다수 연결 시설의 상태·물수지와 관망 결과의 동시 보존."""
import ctypes as C
import json
import math

from waterleague_sim.engine import network
from waterleague_sim.engine.flood_errors import require

FIELDS = ('hydrologyTimeSeconds', 'areaM2', 'surfaceDepthMm', 'soilMoisture', 'storageDepthMm',
          'inflowM3', 'evaporationM3', 'infiltrationM3', 'surfaceOutflowM3', 'drainOutflowM3',
          'initialStorageM3', 'finalStorageM3', 'number', 'drainNodeIndex', 'drainSubcatchmentIndex')


def library_path():
    return network.ROOT / 'tmp/facility-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'CONNECTED_FACILITY_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('facilityObserverVersion') == 1
            and build.get('binarySha256') == network.sha256(path), 'CONNECTED_FACILITY_ENGINE_IDENTITY_INVALID')
    for key, relative in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('builderSha256', 'scripts/build_facility_swmm.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT / relative), 'CONNECTED_FACILITY_ENGINE_IDENTITY_INVALID')
    return build | {'adapterSha256': network.sha256(__file__),
        'baseAdapterSha256': network.sha256(network.__file__),
        'qualityAdapterSha256': network.sha256(network.ROOT / 'simulation/waterleague_sim/engine/network_quality.py')}


class FacilityNetworkSession(network.NetworkSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def snapshot(self):
        result = super().snapshot()
        require(self.lib.wl_connectedLidVersion() == 1, 'CONNECTED_FACILITY_OBSERVER_VERSION_INVALID')
        self.lib.wl_connectedLidCount.argtypes = [C.c_int]
        self.lib.wl_connectedLidRead.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_double), C.c_int,
                                                C.c_char_p, C.c_int]
        rows = []
        for catchment, index in self._names(1).items():
            count = self.lib.wl_connectedLidCount(index)
            require(0 <= count <= 256, 'CONNECTED_FACILITY_OBSERVER_COUNT_INVALID')
            for ordinal in range(count):
                raw = (C.c_double * len(FIELDS))()
                name = C.create_string_buffer(128)
                self._check(self.lib.wl_connectedLidRead(index, ordinal, raw, len(raw), name, len(name)))
                require(all(math.isfinite(v) for v in raw), 'CONNECTED_FACILITY_OBSERVER_NONFINITE')
                row = dict(zip(FIELDS, raw))
                for key in ('soilMoisture', 'storageDepthMm'):
                    if row[key] == -1:
                        row[key] = None
                incoming = row['inflowM3'] + row['initialStorageM3']
                outgoing = math.fsum(row[key] for key in ('evaporationM3', 'infiltrationM3',
                    'surfaceOutflowM3', 'drainOutflowM3', 'finalStorageM3'))
                residual = incoming - outgoing
                tolerance = max(1e-8, .01 * max(incoming, outgoing))
                row.update({'swmmId': name.value.decode(), 'subcatchmentId': catchment,
                    'balanceResidualM3': residual, 'allowedResidualM3': tolerance,
                    'continuityPercent': 100 * residual / max(incoming, outgoing) if max(incoming, outgoing) else 0,
                    'numericalStatus': 'PASSED' if abs(residual) <= tolerance else 'FAILED'})
                rows.append(row)
        result['facilities'] = rows
        return result

    def finish(self):
        result = super().finish()
        failures = [row['swmmId'] for row in result['final']['facilities'] if row['numericalStatus'] != 'PASSED']
        result['facilityQuality'] = {'policyVersion': 'connected-lid-volume-balance-v1',
            'failedFacilityIds': failures, 'status': 'FAILED' if failures else 'PASSED',
            'timeBasis': 'NATIVE_HYDROLOGY_CLOCK_SEPARATE_FROM_ROUTING_CLOCK'}
        if failures:
            result['numericalStatus'] = 'FAILED'
        (self.directory / 'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return result
