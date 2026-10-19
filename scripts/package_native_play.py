"""검증된 원형 계산 DB를 손실 없는 제한 크기 공개 묶음으로 변환."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil

import prepare_native_play_catalog as producer
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial

OUTPUT = source.ROOT / 'backend/src/main/resources/native-play/v1'
CHUNK_BYTES = 32 * 1024**2


def package(directory, expected, output):
    path = directory / 'play.sqlite'
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 공개 계산 묶음·출력 링크 덮어쓰기 금지')
    if (expected['playSha256'] != spatial.file_sha256(path)
            or expected['playBytes'] != path.stat().st_size):
        raise source.TopographyDataError('공개 계산 묶음의 원본 불일치')
    output.mkdir(mode=0o755)
    producer_sha = spatial.file_sha256(__file__)
    full_hash, chunks = hashlib.sha256(), []
    try:
        with source.source_stream(path, expected_sha256=expected['playSha256'], limit=16 * 1024**3) as (stream, _):
            while raw := stream.read(CHUNK_BYTES):
                index = len(chunks)
                full_hash.update(raw)
                payload = gzip.compress(raw, compresslevel=6, mtime=0)
                name = f'part-{index:03}.sqlite.gz'
                with (output / name).open('xb') as target:
                    target.write(payload)
                chunks.append({'file': name, 'bytes': len(raw), 'sha256': source.digest(raw),
                    'gzipBytes': len(payload), 'gzipSha256': source.digest(payload)})
                if (index + 1) % 20 == 0:
                    print(f'공개 계산 묶음 {index + 1}', flush=True)
        if (full_hash.hexdigest() != expected['playSha256'] or spatial.file_sha256(__file__) != producer_sha):
            raise source.TopographyDataError('묶음 생성 중 원형·코드 변경')
        manifest = {'schemaVersion': 1, 'id': 'SEOUL_NGII_REFERENCE_PLAY_V1', 'coordinateSystem': 'EPSG:5186',
            'databaseSha256': expected['playSha256'], 'databaseBytes': expected['playBytes'],
            'sourceSitesSha256': expected['sourceSitesSha256'], 'sourceObjectsSha256': expected['sourceObjectsSha256'],
            'referenceScenario': expected['referenceScenario'], 'generatorSha256': producer_sha,
            'chunkBytes': CHUNK_BYTES, 'chunks': chunks, 'recordCount': expected['counts']['records'],
            'districtKindCounts': expected['districtKindCounts'], 'license': 'KOGL-TYPE1',
            'attribution': '국토지리정보원 수치지도V2.0 · 브이월드 · 서울특별시/서울신용보증재단 자치구 영역 · US EPA 공개 문헌'}
        with (output / 'manifest.json').open('x', encoding='utf-8') as target:
            target.write(source.canonical(manifest) + '\n')
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(exist_ok=True)
    expected = json.loads((source.ROOT / 'data/manifests/seoul-native-play-v1.json').read_text())
    try:
        manifest = package(producer.OUTPUT, expected, args.output.absolute())
    except (OSError, ValueError, KeyError):
        parser.exit(1, '공개 계산 묶음 생성 실패: 원본·출력 확인 필요\n')
    print(source.canonical({'sha256': spatial.file_sha256(args.output / 'manifest.json'),
        'files': len(manifest['chunks']), 'bytes': sum(c['gzipBytes'] for c in manifest['chunks'])}))


if __name__ == '__main__':
    main()
