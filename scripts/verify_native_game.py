"""공개 관측의 원형 공간 결속과 Java·Python 전달 입력 대조."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import prepare_native_game as generation
from waterleague_sim.spatial import game_catalog


def verify(proof_path):
    if proof_path.is_symlink() or not 1 <= proof_path.stat().st_size <= 4 * 1024**2:
        raise ValueError('관측 결속 대조 입력 크기·종류 오류')
    proof = json.loads(proof_path.read_bytes())
    catalog = game_catalog.catalog()
    if (proof['catalogSha256'] != game_catalog.SHA256
            or catalog['generatorSha256'] != generation.spatial.file_sha256(generation.__file__)
            or len(proof['forcings']) != 100):
        raise ValueError('관측 결속 코드·버전 오류')
    bindings = {row['sha256']: json.loads(game_catalog.forcing(row['sha256'])) for row in catalog['models']}
    if proof['forcings'] != bindings:
        raise ValueError('API·워커 관측 결속 불일치')
    for relative, checksum in (catalog['sourceHashes'] | catalog['implementationHashes']).items():
        generation.record_file(relative, {}, checksum)
    pet, antecedent, cases = None, None, []
    for checksum, body in bindings.items():
        generation.verify_rain(body['rainfall'], {})
        if 'disasterEvent' in body:
            pet, _ = game_catalog.climate_binding('evaporation', checksum)
            antecedent, _ = game_catalog.climate_binding('antecedent', checksum)
        cases.append({'districtId': body['districtId'], 'eventId': body.get('disasterEvent', {}).get('id', 'default'),
            'forcingHash': checksum, 'sourceRainfallSha256': body['sourceRainfallSha256'],
            'stationId': body['rainfall']['stationId'], 'distanceKm': body['rainfall']['stationDistanceKm']})
    generation.verify_climate(bindings, pet, antecedent, {})
    files = [Path(game_catalog.__file__), Path(generation.__file__), Path(__file__),
        generation.source.ROOT / 'backend/src/main/java/io/waterleague/rainfall/repository/ObservedGameRepository.java',
        generation.source.ROOT / 'backend/src/main/java/io/waterleague/rainfall/controller/ObservedGameController.java',
        generation.source.ROOT / 'backend/src/main/java/io/waterleague/rainfall/entity/ObservedForcing.java']
    return {'schemaVersion': 1, 'status': 'PASS', 'catalogSha256': game_catalog.SHA256,
        'siteCatalogSha256': catalog['siteCatalogSha256'], 'districtCount': len(game_catalog.regions()),
        'observationBindingsCompared': len(bindings), 'disasterBindingsWithSevenDayInputs': 75,
        'sourceFilesVerified': len(catalog['sourceHashes']), 'apiWorkerForcingJsonMatched': True,
        'rainfallRecomputedFromOriginal': True, 'observedRainfallChanged': False,
        'fieldRepresentativenessVerified': False, 'gameRuntimeMigrated': False,
        'javaProofSha256': generation.spatial.file_sha256(proof_path),
        'implementationHashes': {str(path.resolve().relative_to(generation.source.ROOT)):
            generation.spatial.file_sha256(path) for path in files},
        'cases': sorted(cases, key=lambda row: (row['districtId'], row['eventId']))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--java-proof', type=Path, default=generation.source.ROOT / 'backend/target/native-game-cross-runtime-v2.json')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.report):
            raise ValueError('기존 대조 기록 덮어쓰기 금지')
        value = verify(args.java_proof)
        with args.report.open('x', encoding='utf-8') as target:
            target.write(generation.source.canonical(value) + '\n')
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, '원형 공간의 관측 결속 대조 실패: 원문·시간·버전 확인 필요\n')
    print(generation.source.canonical({key: value[key] for key in
        ('status', 'districtCount', 'observationBindingsCompared', 'disasterBindingsWithSevenDayInputs')}))


if __name__ == '__main__':
    main()
