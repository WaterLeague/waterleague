"""현재 관측 결속의 공개 원문만 실행용 ZIP으로 고정. 개인 자료·인증정보 제외."""
import argparse
import json
import os
from pathlib import Path
import shutil
import zipfile

import prepare_seoul_topography as source
from waterleague_sim.spatial import game_catalog

OUTPUT = source.ROOT / 'backend/src/main/resources/native-weather/v1'


def package(output):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise ValueError('기존 기상 원문 묶음·링크 덮어쓰기 금지')
    output.mkdir()
    entries = []
    registered = dict(game_catalog.catalog()['sourceHashes'])
    implementation_files = {}
    root = source.ROOT
    prior = json.loads((game_catalog.DIRECTORY / 'antecedent.json').read_bytes())
    registered['data/derived/antecedent/generator.py'] = prior['generatorSha256']
    for module, checksum in prior['implementationHashes'].items():
        relative = 'data/derived/antecedent/implementations/' + checksum + '.py'
        registered[relative] = checksum
        implementation_files[checksum] = relative
    for entry in json.loads((game_catalog.DIRECTORY / 'evaporation.json').read_bytes())['entries']:
        body = json.loads((root / 'data/derived/evaporation' / entry['file']).read_bytes())
        for name, checksum in body['implementationHashes'].items():
            current = 'simulation/waterleague_sim/' + ('engine/' if name == 'evapotranspiration.py' else 'ingestion/') + name
            relative = current if source.digest((root / current).read_bytes()) == checksum else 'data/derived/evaporation/implementations/' + checksum + '.py'
            registered[relative] = checksum
            implementation_files[checksum] = relative
    code_sha = source.digest(Path(__file__).read_bytes())
    try:
        with zipfile.ZipFile(output / 'sources.zip', 'x', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9, strict_timestamps=True) as archive:
            for relative, checksum in sorted(registered.items()):
                path = source.project_path(source.ROOT, relative)
                with source.source_stream(path, expected_sha256=checksum, limit=16 * 1024**2) as (stream, _):
                    raw = stream.read()
                if b'authKey=' in raw or b'authkey=' in raw or b'-----BEGIN PRIVATE KEY' in raw:
                    raise ValueError('공개 원문 묶음의 비밀정보 패턴 거부')
                entry = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100444 << 16
                archive.writestr(entry, raw, compresslevel=9)
                entries.append(dict(file=relative, bytes=len(raw), sha256=checksum))
        raw = (output / 'sources.zip').read_bytes()
        if len(raw) > 64 * 1024**2 or sum(entry['bytes'] for entry in entries) > 512 * 1024**2:
            raise ValueError('기상 원문 묶음 크기 상한 초과')
        manifest = dict(schemaVersion=1, id='SEOUL_NATIVE_WEATHER_SOURCES_V1',
            forcingCatalogSha256=game_catalog.SHA256, generatorSha256=code_sha,
            implementationFiles=implementation_files, archive=dict(file='sources.zip', bytes=len(raw), sha256=source.digest(raw)), files=entries,
            license='기상청 공개 관측자료·서울시/국토지리정보원 공개 계보 · 원문별 출처·조건 보존',
            authenticatedRequestsRequiredForReplay=False)
        with (output / 'manifest.json').open('x', encoding='utf-8') as target:
            target.write(source.canonical(manifest) + '\n')
        if source.digest(Path(__file__).read_bytes()) != code_sha:
            raise ValueError('기상 묶음 생성 중 코드 변경')
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = package(args.output.absolute())
    print(source.canonical(dict(files=len(manifest['files']), archive=manifest['archive'],
        manifestSha256=source.digest((args.output / 'manifest.json').read_bytes()))))


if __name__ == '__main__':
    main()
