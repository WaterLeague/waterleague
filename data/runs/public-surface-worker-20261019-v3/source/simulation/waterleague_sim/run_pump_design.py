"""연결 펌프 설계 전후 비교와 동일 플랫폼 오프라인 재현 묶음."""
import argparse
import json
from pathlib import Path
import platform
from zipfile import ZipFile, ZIP_DEFLATED

from .engine.connected_pumps import compile_pumps, CATALOG
from .engine import facility_metrics, pump_network
from .engine.flood_process import EngineProcess
from .engine.flood_errors import require
from .engine.swmm import ROOT
from .ingestion.published_network import digest


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def calculate(source, design, destination, source_provenance):
    require(isinstance(source_provenance, dict) and source_provenance.get('inputSha256') == digest(source)
        and all(isinstance(source_provenance.get(k), str) and source_provenance[k].strip()
                for k in ('title', 'classification', 'attribution', 'licence')), 'PUMP_SOURCE_PROVENANCE_REQUIRED')
    derived, transformation = compile_pumps(source, design)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'original.inp').write_bytes(source)
    (destination/'curve.json').write_bytes(CATALOG.read_bytes())
    write(destination/'design.json', design)
    write(destination/'transformation.json', transformation)
    write(destination/'source-provenance.json', source_provenance)
    (destination/'replay.py').write_bytes(Path(__file__).with_name('pump_replay.py').read_bytes())
    cases = []
    for name, data, module, engine in (
        ('baseline', source, facility_metrics, 'facility_metrics'),
        ('strategy', derived, pump_network, 'pump_network')):
        identity = module.identity()
        (destination/(name+'-engine.bin')).write_bytes(module.library_path().read_bytes())
        write(destination/(name+'-engine.json'), identity)
        with EngineProcess(engine, data.decode(), destination/name, native_duration=True) as process:
            result = process.call('run', 300)['result']
        cases.append({'id': name, 'inputSha256': digest(data), **{key: result[key] for key in (
            'numericalStatus', 'numericalQuality', 'convergence', 'evaluationMetrics', 'durationSeconds',
            'calendarShortfallSeconds', 'timeWindowPolicy', 'initial', 'final')},
            **({'pumpOperation': result['pumpOperation']} if 'pumpOperation' in result else {})})
    archive = ROOT/'tmp/swmm/source.tar.gz'
    require(digest(archive.read_bytes()) == identity['sourceArchiveSha256'], 'PUMP_ENGINE_SOURCE_CHANGED')
    (destination/'engine-source.tar.gz').write_bytes(archive.read_bytes())
    with ZipFile(destination/'implementation.zip', 'x', ZIP_DEFLATED) as bundle:
        files = [*sorted((ROOT/'simulation/waterleague_sim').rglob('*.py')),
                 *sorted((ROOT/'simulation/native').glob('*.inc')),
                 ROOT/'scripts/build_pump_network_swmm.py', ROOT/'scripts/build_facility_metrics_swmm.py',
                 ROOT/'scripts/build_live_swmm.py', ROOT/'scripts/prepare_pump_curve.py',
                 ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock', CATALOG]
        for path in files: bundle.write(path, str(path.relative_to(ROOT)))
    passed = all(c['numericalStatus'] == 'PASSED' for c in cases)
    result = {'schemaVersion': 1, 'classification': 'EXPLICIT_CONNECTED_PUMP_DESIGN_COMPARISON',
        'platform': platform.platform(), 'cases': cases,
        'numericalStatus': 'PASSED' if passed else 'FAILED', 'rankingEligible': False,
        'historicalReconstructionEligible': False, 'siteValidation': False,
        'signedReductionM3': {k: cases[0]['final']['totals'][k]-cases[1]['final']['totals'][k]
                              for k in ('outflowM3', 'floodingM3')} if passed else None,
        'completeInstalledCostKrw': None, 'budgetChargedKrw': None,
        'limitations': transformation['limitations'],
        'artifactFiles': {str(p.relative_to(destination)): digest(p.read_bytes())
                          for p in sorted(destination.rglob('*')) if p.is_file()}}
    write(destination/'result.json', result)
    write(destination/'manifest.json', {str(p.relative_to(destination)): digest(p.read_bytes())
        for p in sorted(destination.rglob('*')) if p.is_file()})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--design', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--provenance', required=True, type=Path)
    args = parser.parse_args()
    result = calculate(args.input.read_bytes(), json.loads(args.design.read_text()), args.output,
                       json.loads(args.provenance.read_text()))
    print(json.dumps({'numericalStatus': result['numericalStatus'], 'signedReductionM3': result['signedReductionM3']}))
