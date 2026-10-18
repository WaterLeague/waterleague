"""펌프의 내부 단계 운전 범위·이송량·축동력을 보존하는 읽기 전용 어댑터."""
import ctypes as C
import json
import math

from . import network, facility_metrics
from .flood_errors import require
from ..ingestion.published_network import records

FIELDS = ('transferredM3', 'runningSeconds', 'flowingSeconds', 'startCount', 'peakFlowM3s',
    'minimumOperatingHeadM', 'maximumOperatingHeadM', 'outsideHeadCurveSeconds',
    'outsideFlowCurveSeconds', 'inRangeShaftEnergyKwh', 'maximumRequiredNpshM',
    'observedSeconds', 'routingSteps')


def library_path():
    return network.ROOT/'tmp/pump-network-swmm-build/install/bin'/network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'PUMP_ENGINE_REQUIRED')
    build = json.loads((path.parent/'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
        and build.get('binarySha256') == network.sha256(path)
        and build.get('facilityObserverVersion') == build.get('metricsVersion') == build.get('pumpObserverVersion') == 1,
        'PUMP_ENGINE_IDENTITY_INVALID')
    for key, source in (('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('pumpObserverSha256', 'simulation/native/pump_snapshot.inc'),
        ('builderSha256', 'scripts/build_pump_network_swmm.py')):
        require(build.get(key) == network.sha256(network.ROOT/source), 'PUMP_ENGINE_IDENTITY_INVALID')
    return build | {'adapterSha256': network.sha256(__file__),
        'facilityMetricsAdapterSha256': network.sha256(facility_metrics.__file__),
        'facilityAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/facility_network.py'),
        'metricsAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/network_metrics.py'),
        'baseAdapterSha256': network.sha256(network.__file__),
        'qualityAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/network_quality.py')}


class PumpNetworkSession(facility_metrics.FacilityMetricsSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def __enter__(self):
        super().__enter__()
        try:
            require(self.input_units == 'CMS' and self.lib.wl_pumpsVersion() == 1, 'PUMP_OBSERVER_VERSION_INVALID')
            self.lib.wl_pumpsBegin.argtypes = [C.c_int, C.c_int, C.c_int]
            self.lib.wl_pumpsRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
            self.lib.wl_pumpsRelease.restype = None
            # 공식 API의 curve 객체 열거 대신 INP에서 처음 등장한 곡선 순서를 사용한다.
            sections = records(self.input_text.encode())[1]
            curve_ids = list(dict.fromkeys(row['tokens'][0].upper() for row in sections.get('CURVES', [])))
            self.pump_ids = [row['tokens'][0] for row in sections.get('PUMPS', [])
                             if row['tokens'][0].startswith('WLPU_')]
            for name in self.pump_ids:
                key = name.upper()
                require(key+'_P' in curve_ids and key+'_N' in curve_ids, 'PUMP_OBSERVER_CURVE_MISSING')
                self._check(self.lib.wl_pumpsBegin(self.links[name], curve_ids.index(key+'_P'), curve_ids.index(key+'_N')))
            return self
        except BaseException:
            self.close()
            raise

    def pump_state(self):
        rows = []
        for name in self.pump_ids:
            raw = (C.c_double*len(FIELDS))()
            self._check(self.lib.wl_pumpsRead(self.links[name], raw, len(raw)))
            require(all(math.isfinite(v) for v in raw), 'PUMP_OBSERVER_NONFINITE')
            row = dict(zip(FIELDS, raw)) | {'linkId': name}
            valid = row['outsideHeadCurveSeconds'] == row['outsideFlowCurveSeconds'] == 0
            row['curveStatus'] = 'PASSED' if valid else 'FAILED'
            row['shaftEnergyKwh'] = row['inRangeShaftEnergyKwh'] if valid else None
            row['electricEnergyKwh'] = None
            row['cavitationStatus'] = 'NOT_EVALUATED'
            rows.append(row)
        return {'method': 'NATIVE_ROUTING_STEP_PUMP_OBSERVER_V1', 'pumps': rows,
            'volumeIntegration': 'TRAPEZOIDAL_INTERNAL_TRANSFER_NOT_EXTERNAL_OUTFLOW',
            'shaftPowerIntegration': 'END_OF_NATIVE_STEP_RECTANGLE_MANUFACTURER_P_Q_CURVE',
            'curveStatus': 'PASSED' if all(v['curveStatus'] == 'PASSED' for v in rows) else 'FAILED',
            'rankingEligible': False}

    def finish(self):
        pump = self.pump_state()
        result = super().finish()
        for row in pump['pumps']:
            delivery = result['final']['nodes'].get(row['linkId']+'_D')
            require(delivery is not None, 'PUMP_DELIVERY_NODE_REQUIRED')
            row['deliveryFloodingM3'] = delivery['floodingM3']
            row['deliveryNodeId'] = row['linkId']+'_D'
            row['deliveryStatus'] = 'PASSED' if delivery['floodingM3'] <= 1e-9 else 'FAILED'
        pump['deliveryStatus'] = 'PASSED' if all(r['deliveryStatus'] == 'PASSED' for r in pump['pumps']) else 'FAILED'
        result['pumpOperation'] = pump
        if pump['curveStatus'] != 'PASSED' or pump['deliveryStatus'] != 'PASSED': result['numericalStatus'] = 'FAILED'
        (self.directory/'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2)+'\n')
        return result

    def close(self):
        if self.opened: self.lib.wl_pumpsRelease()
        super().close()
