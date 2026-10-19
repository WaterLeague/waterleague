"""시설·직접 강우·지표 교환을 한 네이티브 상태에서 관측."""
import json

from waterleague_sim.engine import network, network_exchange, network_metrics, facility_network, network_rainfall
from waterleague_sim.engine.flood_errors import require


def library_path():
    return network.ROOT / 'tmp/coupled-rainfall-facility-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'COUPLED_RAINFALL_FACILITY_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('binarySha256') == network.sha256(path)
            and all(build.get(key) == 1 for key in ('facilityObserverVersion', 'exchangeVersion', 'metricsVersion', 'rainfallVersion')),
            'COUPLED_RAINFALL_FACILITY_ENGINE_IDENTITY_INVALID')
    for key, relative in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('exchangeSha256', 'simulation/native/network_exchange.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('rainfallSha256', 'simulation/native/network_rainfall.inc'),
        ('builderSha256', 'scripts/build_coupled_rainfall_facility_swmm.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT / relative),
                'COUPLED_RAINFALL_FACILITY_ENGINE_IDENTITY_INVALID')
    return build | {'adapterSha256': network.sha256(__file__),
        'rainfallAdapterSha256': network.sha256(network_rainfall.__file__),
        'facilityAdapterSha256': network.sha256(facility_network.__file__),
        'metricsAdapterSha256': network.sha256(network_metrics.__file__),
        'exchangeAdapterSha256': network.sha256(network_exchange.__file__),
        'baseAdapterSha256': network.sha256(network.__file__),
        'qualityAdapterSha256': network.sha256(network.ROOT / 'simulation/waterleague_sim/engine/network_quality.py')}


class CoupledRainfallFacilitySession(network_rainfall.RainfallObserver,
                                    facility_network.FacilityNetworkSession, network_metrics.MetricsNetworkSession):
    # 세 관측기는 한 SWMM 상태만 읽으며 시설 실패를 강우 수지 성공으로 덮지 않는다.
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)
