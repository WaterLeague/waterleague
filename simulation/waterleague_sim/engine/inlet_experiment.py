"""원 관로·명시적 격자·빗물받이 설계의 한 실행과 원장 보존."""
from copy import deepcopy
import json
from pathlib import Path

from .connected_inlets import compile_inlets
from .flood_errors import require
from .flood_process import EngineProcess
from ..ingestion.conduit_refinement import refine, assess_virtual_nodes
from ..ingestion.network_variant import derive_compiled
from ..ingestion.published_network import digest


def prepare(raw, design, refinement, numerical):
    # 원 설계를 먼저 검사하여 해시 재결속으로 잘못된 원 연결을 허용하지 않는다.
    compile_inlets(raw, design)
    refined, mesh = refine(raw, refinement)
    refined, settings = derive_compiled(refined, numerical)
    derived_design = deepcopy(design)
    derived_design['sourceNetworkSha256'] = digest(refined)
    result, inlet = compile_inlets(refined, derived_design)
    return result, {'sourceNetworkSha256': digest(raw), 'sourceDesign': deepcopy(design),
        'refinement': mesh, 'numerical': settings, 'inlet': inlet,
        'derivedNetworkSha256': digest(result), 'rankingEligible': False}


def assess_result(transformation, native):
    check = assess_virtual_nodes(transformation['refinement'], native)
    failures = list(native['numericalQuality']['failureReasons'])
    if native['facilityQuality']['status'] != 'PASSED':
        failures.append('CONNECTED_FACILITY_BALANCE_FAILED')
    if not native['evaluationMetrics']['complete']:
        failures.append('OUTFALL_METRICS_INCOMPLETE')
    if native['numericalStatus'] != 'PASSED' and not failures:
        failures.append('NATIVE_NUMERICAL_FAILURE')
    if check['status'] != 'PASSED':
        failures.append('UNMAPPED_COMPUTATIONAL_NODE_FLOODING')
    return {'virtualNodes': check, 'nativeNumericalStatus': native['numericalStatus'],
        'numericalStatus': 'FAILED' if failures else 'PASSED', 'failureReasons': failures}


def run(raw, design, refinement, numerical, directory, *, frame_seconds=60):
    prepared, transformation = prepare(raw, design, refinement, numerical)
    target = Path(directory)
    require(not target.exists(), 'INLET_EXPERIMENT_OUTPUT_EXISTS')
    target.mkdir(parents=True)
    def write(name, value):
        (target/name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    (target/'original.inp').write_bytes(raw)
    (target/'prepared.inp').write_bytes(prepared)
    write('design.json', design)
    write('refinement.json', refinement)
    write('numerical-profile.json', numerical)
    write('transformation.json', transformation)
    with EngineProcess('inlet_network', prepared.decode(), target/'network', native_duration=True) as engine:
        native = engine.call('run', frame_seconds)['result']
    result = {'schemaVersion': 1, 'classification': 'NUMERICAL_INLET_REFINEMENT_NOT_SITE_VALIDATION',
        'rankingEligible': False, 'transformationSha256': digest((target/'transformation.json').read_bytes()),
        'codeSha256': digest(Path(__file__).read_bytes()), **assess_result(transformation, native),
        'nativeResultSha256': digest((target/'network/network-result.json').read_bytes())}
    write('experiment-result.json', result)
    return result, native
