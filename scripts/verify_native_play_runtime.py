"""공개 묶음만으로 Java 조회·Python 계산의 원형/조건 일치 검증."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from waterleague_sim.spatial import play_bundle
from waterleague_sim.engine import continuous

FORCING = source.ROOT / 'data/models/seongsu-421-20240718.json'
FORCING_SHA256 = 'fff031781cebc7f1b1f8e6cd0ed284c2166f688d80a2c70a2e4c24ee2df438c3'


def verify(proof_path, engine_output):
    if (not 1 <= proof_path.stat().st_size <= 64 * 1024**2
            or engine_output is not None and os.path.lexists(engine_output)):
        raise ValueError('재현 입력·출력 제한')
    proof = json.loads(proof_path.read_text())
    expected = json.loads((source.ROOT / 'data/manifests/seoul-native-play-v1.json').read_text())
    reader = play_bundle.open_catalog()
    if (proof['catalogSha256'] != reader.sha256 or proof['bundleSha256'] != play_bundle.MANIFEST_SHA256
            or proof['coordinateSystem'] != 'EPSG:5186' or len(proof['cases']) != 25):
        raise ValueError('두 런타임의 공간 버전 불일치')
    compared, districts = 0, set()
    for case in proof['cases']:
        district = case['districtId']
        if district in districts:
            raise ValueError('자치구 중복')
        districts.add(district)
        cells = reader.bounds(case['bounds'], district=district, limit=2000)
        if cells != case['sites'] or not cells:
            raise ValueError('API·워커의 원형·조건·조회 결과 불일치')
        compared += len(cells)
    if districts != {key.split(':')[0] for key in expected['districtKindCounts']}:
        raise ValueError('25개 구 조회 누락')
    raw = FORCING.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FORCING_SHA256:
        raise ValueError('고정 관측 입력 불일치')
    rain = json.loads(raw)['rainfall']
    if engine_output is not None:
        engine_output.mkdir(mode=0o700)
    results = []
    for case in expected['validation']['engineValidation']['cases'] if engine_output is not None else []:
        cell_id, district, facility = case['candidateId'], case['districtId'], case['facilityType']
        model = reader.model(cell_id, district=district)
        model['rainfall'] = rain
        placement = reader.placement(cell_id, facility, case['areaM2'], district=district)
        result = continuous.experiment(model, placement, engine_output / facility.lower())
        volume = placement['areaM2'] * math.fsum(rain['depthsMm']) / 1000
        if not math.isclose(result['strategy']['final']['lidInflowM3'], volume, abs_tol=1e-5, rel_tol=1e-6):
            raise ValueError('공개 묶음의 직접 강우 체적 불일치')
        results.append({'candidateId': cell_id, 'districtId': district, 'facilityType': facility,
            'areaM2': placement['areaM2'], 'costKrw': placement['costKrw'], 'directRainVolumeMatched': True,
            'engine': result['strategy']['engine'],
            'resultSha256': spatial.file_sha256(engine_output / facility.lower() / 'result.json')})
    java = source.ROOT / 'backend/src/main/java/io/waterleague/spatial'
    java_sources = [java / name for name in ('repository/NativePlayBundle.java', 'repository/NativePlayRepository.java',
        'service/NativeGeometry.java', 'controller/NativePlayController.java')]
    return {'schemaVersion': 1, 'status': 'PASS', 'bundleSha256': play_bundle.MANIFEST_SHA256,
        'databaseSha256': reader.sha256, 'verifierSha256': spatial.file_sha256(__file__),
        'workerBundleReaderSha256': spatial.file_sha256(play_bundle.__file__),
        'workerCatalogReaderSha256': spatial.file_sha256(source.ROOT / 'simulation/waterleague_sim/spatial/play_catalog.py'),
        'javaSources': {str(path.relative_to(source.ROOT)): spatial.file_sha256(path) for path in java_sources},
        'javaProofSha256': spatial.file_sha256(proof_path), 'districtsCompared': len(districts),
        'apiWorkerCellsCompared': compared, 'fullCellJsonMatched': True,
        'forcingSourceSha256': FORCING_SHA256, 'forcingUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
        'engineCases': results, 'engineCasesVerified': len(results) == 6, 'privateOriginalsRequired': False,
        'antecedentSpinupApplied': False, 'rankingEligible': False, 'gameRuntimeMigrated': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--java-proof', type=Path, default=source.ROOT / 'backend/target/native-play-cross-runtime-v1.json')
    parser.add_argument('--engine-output', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.report):
            raise ValueError('기존 대조 기록 덮어쓰기 금지')
        report = verify(args.java_proof, args.engine_output)
        with args.report.open('x', encoding='utf-8') as target:
            target.write(source.canonical(report) + '\n')
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, '공개 공간 런타임 대조 실패: 버전·원형·조건·계산 확인 필요\n')
    print(source.canonical({'status': report['status'], 'districts': report['districtsCompared'],
        'cells': report['apiWorkerCellsCompared'], 'facilities': len(report['engineCases'])}))


if __name__ == '__main__':
    main()
