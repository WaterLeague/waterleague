"""관측 선행 기간을 시설·관망·지표의 같은 시계로 연결."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.initialized_facilities import evaluation_ledger as facility_ledger
from waterleague_sim.engine.network import _TOTAL_FIELDS
from waterleague_sim.engine.network_quality import routing_balance
from waterleague_sim.forcing.network_initialization import prepare_initialized_network, METHOD as NETWORK_METHOD
from waterleague_sim.forcing.surface_initialization import prepare_initialized_surface, evaluation_ledger as surface_ledger

METHOD = 'OBSERVED_COUPLED_ANTECEDENT_CONTINUOUS_V1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass
class InitializedCoupling:
    model: dict
    schedule: object
    network: object
    summary: dict


def prepare_initialized_coupling(model):
    initialization = model.get('initialization')
    require(isinstance(initialization, dict) and initialization.get('method') == METHOD,
            'COUPLED_INITIALIZATION_INVALID')
    require(not model.get('networkForcing') and not model.get('surfaceRainfall'),
            'COUPLED_INITIALIZATION_EXTERNAL_FORCING_CONFLICT')
    rain = model.get('observedRainfall')
    metrics = model.get('evaluationMetrics')
    require(isinstance(rain, dict) and isinstance(metrics, dict)
            and metrics.get('startMilliseconds') == 0
            and metrics.get('endMilliseconds') == model['durationSeconds']*1000,
            'COUPLED_INITIALIZATION_EVALUATION_REQUIRED')
    require('evaluationMetrics' not in model['surface'] and 'evaluationMetrics' not in model['network'],
            'COUPLED_METRICS_SPECIFICATION_CONFLICT')
    evaporation = model['surface'].get('evaporation')
    require(isinstance(evaporation, dict) and evaporation.get('reference') == rain.get('evaporationReference'),
            'COUPLED_INITIALIZATION_WEATHER_MISMATCH')
    network = prepare_initialized_network(model['network'], rain, initialization | {'method': NETWORK_METHOD})
    surface, combined, schedule, seconds = prepare_initialized_surface(
        model['surface'] | {'evaluationMetrics': metrics}, rain,
        initialization | {'method': 'OBSERVED_ANTECEDENT_CONTINUOUS_V1'})
    require(seconds == network.summary['warmupSeconds']
            and model['durationSeconds'] == network.summary['evaluationSeconds'],
            'COUPLED_INITIALIZATION_CLOCK_MISMATCH')
    value = deepcopy(model)
    value.pop('initialization')
    value.update(network=network.model, surface=surface, observedRainfall=combined,
                 durationSeconds=seconds + model['durationSeconds'],
                 evaluationMetrics=surface.pop('evaluationMetrics'))
    summary = {'schemaVersion': 1, 'method': METHOD, 'requestSha256': digest(model),
        'preparedModelSha256': digest(value), 'warmupSeconds': seconds,
        'evaluationSeconds': model['durationSeconds'], 'network': network.summary,
        'scoreExcludesWarmup': True, 'statePolicy': 'SAME_LIVE_ENGINES_NO_STATE_TRANSPLANT',
        'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return InitializedCoupling(value, schedule, network, summary)


def evaluation_ledger(origin, final):
    a, b = origin['network'], final['network']
    start, end = a['totals']['timeSeconds'], b['totals']['timeSeconds']
    require(0 < start < end and all(math.isclose(state['surface']['surface']['timeSeconds'], time,
            abs_tol=1e-7, rel_tol=0) for state, time in ((origin, start), (final, end))),
            'COUPLED_INITIALIZATION_BOUNDARY_CLOCK_MISMATCH')
    totals = {k: b['totals'][k]-a['totals'][k] for k in _TOTAL_FIELDS[3:]}
    totals.update(initialStorageM3=a['totals']['storageM3'], storageM3=b['totals']['storageM3'])
    routing = routing_balance(totals)
    surface = surface_ledger(origin['surface']['surface'], final['surface']['surface'])
    require(set(origin['ports']) == set(final['ports']), 'COUPLED_INITIALIZATION_PORTS_MISMATCH')
    ports = {}
    for key, row in final['ports'].items():
        ports[key] = {field: row[field]-origin['ports'][key][field]
                      for field in ('networkToSurfaceM3', 'surfaceToNetworkM3')}
        require(all(math.isfinite(v) and v >= -1e-10 for v in ports[key].values()),
                'COUPLED_INITIALIZATION_EXCHANGE_COUNTER_REVERSED')
    outward = math.fsum(row['networkToSurfaceM3'] for row in ports.values())
    inward = math.fsum(row['surfaceToNetworkM3'] for row in ports.values())
    exchange = final['surfaceExchange']['exchangeNetInflowM3']-origin['surfaceExchange']['exchangeNetInflowM3']
    require(math.isclose(outward-inward, exchange, abs_tol=1e-8, rel_tol=0),
            'COUPLED_INITIALIZATION_EXCHANGE_MISMATCH')
    incoming = math.fsum(totals[k] for k in ('dryWeatherInflowM3', 'runoffInflowM3',
        'groundwaterInflowM3', 'rdiiInflowM3', 'externalInflowM3')) - inward
    outgoing = math.fsum(totals[k] for k in ('outflowM3', 'floodingM3', 'evaporationM3',
        'seepageM3', 'reactionLossM3')) - outward
    initial = totals['initialStorageM3'] + surface['initialStorageM3']
    storage = totals['storageM3'] + surface['finalStorageM3']
    external = surface['sourceNetInflowM3']-exchange+surface['boundaryNetInflowM3']
    residual = initial + incoming + external - outgoing - storage
    tolerance = max(1e-8, .01*max(initial+max(0, incoming)+max(0, external), storage+max(0, outgoing)))
    surface_tolerance = max(1e-8, .01*max(surface['initialStorageM3']
        + max(0, surface['sourceNetInflowM3'])+max(0, surface['boundaryNetInflowM3']), surface['finalStorageM3']))
    facilities = facility_ledger(a, b) if 'facilities' in a or 'facilities' in b else None
    passed = (abs(residual) <= tolerance and abs(surface['balanceResidualM3']) <= surface_tolerance
        and abs(routing['residualM3']) <= routing['allowedResidualM3']
        and (facilities is None or facilities['numericalStatus'] == 'PASSED'))
    return {'durationSeconds': end-start, 'numericalStatus': 'PASSED' if passed else 'FAILED',
        'routing': {'totals': totals, 'balance': routing}, 'surface': surface,
        'facilities': facilities, 'ports': ports,
        'coupled': {'initialStorageM3': initial, 'finalStorageM3': storage,
            'networkExternalInflowM3': incoming, 'networkExternalOutflowAndLossM3': outgoing,
            'surfaceExternalNetInflowM3': external, 'balanceResidualM3': residual,
            'allowedResidualM3': tolerance, 'exchangeCancellationResidualM3': outward-inward-exchange},
        'scope': 'SEPARATE_FACILITIES_AND_COUPLED_ROUTING_SURFACE_CONTROL_VOLUMES'}
