"""명시적 관망 이용조의 전후 비교와 원 입력·엔진·결과 보존."""
import argparse
import json
from pathlib import Path
import platform
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from .engine import facility_metrics
from .engine.cistern_network import compile_cistern
from .engine.connected_storage import result_summary
from .engine.flood_errors import require
from .engine.flood_process import EngineProcess
from .engine.swmm import ROOT
from .ingestion.published_network import digest


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def calculate(raw, design, directory):
    derived, metadata = compile_cistern(raw, design)
    directory = Path(directory)
    require(not directory.exists(), 'CISTERN_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    write(directory/'design.json', design)
    write(directory/'transformation.json', metadata)
    engine = facility_metrics.identity() | {'platform': platform.platform()}
    source = ROOT/'tmp/swmm/source.tar.gz'
    require(digest(source.read_bytes()) == engine['sourceArchiveSha256'], 'CISTERN_ENGINE_SOURCE_CHANGED')
    for source_path, name in ((facility_metrics.library_path(), 'engine.bin'),
            (facility_metrics.library_path().parent/'network-build.json', 'engine-build.json'),
            (source, 'engine-source.tar.gz'),
            (Path(__file__).with_name('watershed_replay.py'), 'replay.py')):
        shutil.copyfile(source_path, directory/name)
    with ZipFile(directory/'implementation.zip', 'x', ZIP_DEFLATED) as archive:
        files = [*sorted((ROOT/'simulation/waterleague_sim').rglob('*.py')),
            ROOT/'simulation/native/network_snapshot.inc', ROOT/'simulation/native/connected_lid_snapshot.inc',
            ROOT/'simulation/native/network_metrics.inc', ROOT/'scripts/build_facility_metrics_swmm.py',
            ROOT/'scripts/build_live_swmm.py', ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock']
        for path in files:
            archive.write(path, str(path.relative_to(ROOT)))
    cases = []
    for name, inp in (('baseline', raw), ('strategy', derived)):
        with EngineProcess('facility_metrics', inp.decode('utf-8-sig'), directory/name,
                           native_duration=True) as process:
            result = process.call('run', 300)['result']
        case = {'id': name, 'inputSha256': digest(inp),
            **{key: result[key] for key in ('numericalStatus', 'numericalQuality', 'convergence',
                'runoffContinuityPercent', 'routingContinuityPercent', 'evaluationMetrics',
                'timeWindowPolicy', 'calendarShortfallSeconds')}, 'totals': result['final']['totals']}
        if name == 'strategy':
            case['cistern'] = result_summary(metadata, result['initial'], result['final'])
            if case['cistern']['numericalStatus'] != 'PASSED':
                case['numericalStatus'] = 'FAILED'
        cases.append(case)
    passed = all(case['numericalStatus'] == 'PASSED' for case in cases)
    require(cases[0]['evaluationMetrics']['specificationSha256']
        == cases[1]['evaluationMetrics']['specificationSha256'], 'CISTERN_METRIC_WINDOW_CHANGED')
    result = {'schemaVersion': 1, 'classification': 'EXPLICIT_NETWORK_CISTERN_DESIGN_COMPARISON',
        'engine': engine, 'design': metadata, 'cases': cases,
        'numericalStatus': 'PASSED' if passed else 'FAILED',
        'signedReductionM3': {key: cases[0]['totals'][key]-cases[1]['totals'][key]
            for key in ('outflowM3', 'floodingM3')} if passed else None,
        'signedPeakReductionM3s': (cases[0]['evaluationMetrics']['combined']['peakOutwardM3s']
            -cases[1]['evaluationMetrics']['combined']['peakOutwardM3s']) if passed else None,
        'routingRunoffInflowDifferenceM3': cases[1]['totals']['runoffInflowM3']-cases[0]['totals']['runoffInflowM3'],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'completeInstalledCostKrw': None, 'budgetChargedKrw': None,
        'limitations': metadata['limitations']+[
            '명시적 집수·이용조 설계의 관망 수리 비교; 실제 현장 지붕·높이·홈통 검증 아님',
            '관망 월류 감소와 순저류는 재이용 수요 충족·지표 침수 저감의 확정값이 아님',
            '원 자료의 시간 창·초기 상태 사용, 선행 관측 수위로 초기화된 재난 복원 아님']}
    result['artifactFiles'] = {str(path.relative_to(directory)): digest(path.read_bytes())
        for path in sorted(directory.rglob('*')) if path.is_file()}
    write(directory/'result.json', result)
    write(directory/'manifest.json', {str(path.relative_to(directory)): digest(path.read_bytes())
        for path in sorted(directory.rglob('*')) if path.is_file()})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--design', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = calculate(args.input.read_bytes(), json.loads(args.design.read_text()), args.output)
    print(json.dumps({key: result[key] for key in ('numericalStatus', 'signedReductionM3',
        'signedPeakReductionM3s', 'routingRunoffInflowDifferenceM3')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
