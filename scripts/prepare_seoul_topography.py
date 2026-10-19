"""서울 수치지형도 원본 검증과 중복 없는 불변 입력 카탈로그 생성."""
import argparse
from collections import Counter
from contextlib import closing, contextmanager
from functools import lru_cache
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import struct
import sys
import unicodedata
import zipfile
import zlib

import pyproj

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path('data/manifests/vworld-seoul-topography-20260307.json')
OUTPUT = Path('data/private/vworld-seoul-topography-20260307/catalog-v1')
MAX_SOURCE_BYTES = 128 * 1024**2
MAX_MEMBER_BYTES = 64 * 1024**2
MAX_ARCHIVE_BYTES = 512 * 1024**2
MAX_TOTAL_BYTES = 64 * 1024**3
MAX_ENTRIES = 2048
MAX_TILES = 10_000
LAYER_PATTERN = r'N[13][ALP]_[A-Z]\d{7}'
COMPONENT_PATTERN = re.compile(rf'({LAYER_PATTERN})\.(shp|shx|dbf|prj|cpg)')
HASH_PATTERN = re.compile(r'[0-9a-f]{64}')


class TopographyDataError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project_path(root, relative):
    if not isinstance(relative, str):
        raise TopographyDataError('프로젝트 상대 경로 오류')
    path = PurePosixPath(relative)
    if (not path.parts or path.is_absolute()
            or '..' in path.parts or '\\' in relative or ':' in relative
            or path.as_posix() != relative):
        raise TopographyDataError('프로젝트 상대 경로 오류')
    result = root
    for part in path.parts:
        result = result / part
        if result.is_symlink():
            raise TopographyDataError('원본 경로의 링크 금지')
    return result


@contextmanager
def source_stream(path, expected_bytes=None, expected_sha256=None, limit=MAX_SOURCE_BYTES):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise TopographyDataError('원본 파일 열기 실패') from exc
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or expected_bytes is not None and info.st_size != expected_bytes):
            raise TopographyDataError('원본 종류·크기 불일치')
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if expected_sha256 is not None and checksum != expected_sha256:
            raise TopographyDataError('등록 원본 SHA-256 불일치')
        stream.seek(0)
        yield stream, checksum
        stream.seek(0)
        if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
            raise TopographyDataError('검사 중 원본 변경')


def archive_members(archive):
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ENTRIES:
        raise TopographyDataError('압축 구성 수 제한 초과')
    names, total = set(), 0
    result = []
    for entry in entries:
        name = unicodedata.normalize('NFC', entry.filename)
        key = name.casefold()
        mode = stat.S_IFMT(entry.external_attr >> 16)
        # 배포 파일은 평면 구조이므로 디렉터리도 허용하지 않는다.
        if (entry.orig_filename != entry.filename or '/' in name or '\\' in name or ':' in name
                or name in ('', '.', '..') or key in names or entry.flag_bits & 1
                or entry.is_dir() or mode not in (0, stat.S_IFREG)
                or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise TopographyDataError('압축 경로·중복·링크·암호화·방식 오류')
        if (not 0 <= entry.file_size <= MAX_MEMBER_BYTES
                or entry.file_size > max(1, entry.compress_size) * 4096):
            raise TopographyDataError('압축 구성 크기·압축률 제한 초과')
        names.add(key)
        total += entry.file_size
        result.append((name, entry))
    if total > MAX_ARCHIVE_BYTES:
        raise TopographyDataError('압축 해제 총 크기 제한 초과')
    return sorted(result, key=lambda item: item[0])


def read_member(archive, entry):
    chunks, total = [], 0
    with archive.open(entry) as source:
        while chunk := source.read(1024**2):
            total += len(chunk)
            if total > min(MAX_MEMBER_BYTES, entry.file_size):
                raise TopographyDataError('실제 압축 해제 크기 제한 초과')
            chunks.append(chunk)
    if total != entry.file_size:
        raise TopographyDataError('실제 압축 해제 크기 불일치')
    return b''.join(chunks)


def dbf_schema(data, encoding, declared_encoding=None):
    if len(data) < 33 or data[0] != 3:
        raise TopographyDataError('지원하지 않는 DBF 형식')
    count, header_size, record_size = struct.unpack_from('<IHH', data, 4)
    if (header_size < 33 or (header_size - 33) % 32 or data[header_size - 1:header_size] != b'\r'
            or record_size < 1 or count > 1_000_000
            or len(data) not in (header_size + count * record_size, header_size + count * record_size + 1)
            or len(data) > header_size + count * record_size and data[-1] != 0x1a):
        raise TopographyDataError('DBF 헤더·행 길이 오류')
    fields, offset, names = [], 1, set()
    for position in range(32, header_size - 1, 32):
        raw = data[position:position + 32]
        name = raw[:11].split(b'\0', 1)[0].decode(encoding, errors='strict')
        kind, width, decimals = chr(raw[11]), raw[16], raw[17]
        if (not name or name in names or kind not in ('C', 'N', 'F', 'D', 'L') or width < 1
                or kind in ('N', 'F') and decimals >= width):
            raise TopographyDataError('DBF 필드 정의 오류')
        fields.append({'name': name, 'type': kind, 'width': width, 'decimals': decimals, 'offset': offset})
        offset += width
        names.add(name)
    if offset != record_size:
        raise TopographyDataError('DBF 필드·행 길이 불일치')
    deleted, declaration_mismatches = 0, 0
    for position in range(header_size, header_size + count * record_size, record_size):
        row = data[position:position + record_size]
        if row[0] not in (32, 42):
            raise TopographyDataError('DBF 삭제 표식 오류')
        deleted += row[0] == 42
        mismatched = False
        for field in fields:
            start = field['offset']
            raw = row[start:start + field['width']]
            raw.decode(encoding if field['type'] == 'C' else 'ascii', errors='strict')
            if declared_encoding and field['type'] == 'C':
                try:
                    raw.decode(declared_encoding, errors='strict')
                except UnicodeDecodeError:
                    mismatched = True
        declaration_mismatches += mismatched
    return {'recordCount': count, 'deletedRecordCount': deleted, 'headerBytes': header_size,
            'recordBytes': record_size, 'languageDriverId': data[29], 'fields': fields,
            'encodingDeclarationMismatchRecords': declaration_mismatches}


def shape_header(data):
    if (len(data) < 100 or struct.unpack_from('>I', data)[0] != 9994 or data[4:24] != b'\0' * 20
            or struct.unpack_from('>I', data, 24)[0] * 2 != len(data)
            or struct.unpack_from('<I', data, 28)[0] != 1000):
        raise TopographyDataError('SHP/SHX 헤더·크기 오류')
    shape_type = struct.unpack_from('<I', data, 32)[0]
    bounds = struct.unpack_from('<4d', data, 36)
    if shape_type not in (1, 3, 5) or not all(math.isfinite(v) for v in bounds):
        raise TopographyDataError('SHP/SHX 도형 종류·범위 오류')
    return shape_type, bounds


@lru_cache(maxsize=64)
def verify_crs(wkt):
    crs = pyproj.CRS.from_wkt(wkt)
    target = pyproj.CRS.from_epsg(5186)
    operation = crs.coordinate_operation
    expected = target.coordinate_operation
    parameters = {p.code: p.value * p.unit_conversion_factor for p in operation.params} if operation else {}
    target_parameters = {p.code: p.value * p.unit_conversion_factor for p in expected.params}
    # ESRI WKT의 각도 단위 반올림은 허용하되 데이텀과 투영 매개변수는 직접 대조한다.
    if (crs.datum != target.datum or crs.prime_meridian != target.prime_meridian
            or operation is None or operation.method_code != expected.method_code
            or parameters.keys() != target_parameters.keys()
            or any(not math.isclose(parameters[k], v, rel_tol=1e-15, abs_tol=1e-15)
                   for k, v in target_parameters.items())
            or not crs.is_projected or len(crs.axis_info) != 2
            or any(axis.unit_conversion_factor != 1 for axis in crs.axis_info)):
        raise TopographyDataError('EPSG:5186 미터 좌표계 불일치')


def verify_shape_content(content, kind):
    if kind == 0:
        if len(content) != 4:
            raise TopographyDataError('빈 SHP 레코드 길이 오류')
        return
    if kind == 1:
        if len(content) != 20:
            raise TopographyDataError('점 SHP 레코드 길이 오류')
        coordinates = content[4:]
    else:
        if len(content) < 44:
            raise TopographyDataError('선·면 SHP 레코드 길이 오류')
        parts, points = struct.unpack_from('<II', content, 36)
        if not 1 <= parts <= points or len(content) != 44 + parts * 4 + points * 16:
            raise TopographyDataError('SHP 부분·꼭짓점 수 오류')
        indexes = struct.unpack_from(f'<{parts}I', content, 44)
        if indexes[0] != 0 or indexes[-1] >= points or any(a >= b for a, b in zip(indexes, indexes[1:])):
            raise TopographyDataError('SHP 부분 인덱스 오류')
        if not all(math.isfinite(v) for v in struct.unpack_from('<4d', content, 4)):
            raise TopographyDataError('SHP 레코드 범위 오류')
        coordinates = content[44 + parts * 4:]
    if any(not math.isfinite(v) for pair in struct.iter_unpack('<2d', coordinates) for v in pair):
        raise TopographyDataError('SHP 비유한 좌표 오류')


def inspect_layer(layer, components):
    if not {'shp', 'shx', 'dbf', 'prj'} <= components.keys():
        raise TopographyDataError('SHP/SHX/DBF/PRJ 구성 누락')
    wkt = components['prj'].decode('utf-8-sig', errors='strict')
    verify_crs(wkt)
    cpg = components.get('cpg')
    declared = cpg.decode('ascii', errors='strict').strip() if cpg is not None else None
    if declared is not None and declared.upper() not in ('EUC-KR', 'CP949', '949'):
        raise TopographyDataError('지원하지 않는 CPG 문자셋')
    # EUC-KR 표기에도 CP949 확장 문자가 있어 원 선언과 불일치 수를 함께 보존한다.
    encoding = 'cp949'
    dbf = dbf_schema(components['dbf'], encoding, 'euc_kr' if declared and declared.upper() == 'EUC-KR' else None)
    shp, shx = components['shp'], components['shx']
    shape_type, bounds = shape_header(shp)
    if (shape_header(shx) != (shape_type, bounds) or (len(shx) - 100) % 8
            or (len(shx) - 100) // 8 != dbf['recordCount']
            or shape_type != {'A': 5, 'L': 3, 'P': 1}[layer[2]]):
        raise TopographyDataError('SHP/SHX/DBF 도형 종류·레코드 수 불일치')
    cursor, nulls = 100, 0
    for index in range(dbf['recordCount']):
        offset, length = struct.unpack_from('>II', shx, 100 + index * 8)
        length *= 2
        if offset * 2 != cursor or length < 4 or cursor + 8 + length > len(shp):
            raise TopographyDataError('SHX 오프셋·레코드 길이 오류')
        number, actual_length = struct.unpack_from('>II', shp, cursor)
        kind = struct.unpack_from('<I', shp, cursor + 8)[0]
        if number != index + 1 or actual_length * 2 != length or kind not in (0, shape_type):
            raise TopographyDataError('SHP 레코드 번호·종류·길이 불일치')
        verify_shape_content(memoryview(shp)[cursor + 8:cursor + 8 + length], kind)
        nulls += kind == 0
        cursor += 8 + length
    if cursor != len(shp):
        raise TopographyDataError('SHP 미참조 레코드 존재')
    return {'layer': layer, 'shapeType': shape_type, 'boundsProjected': bounds, 'dbf': dbf,
            'encoding': encoding, 'declaredCpg': declared, 'nativeCrs': 'EPSG:5186', 'originalWkt': wkt,
            'storedCoordinateOrder': 'x=easting,y=northing', 'encodingPolicy': 'EXPLICIT_CP949_STRICT',
            'nullShapeCount': nulls, 'geometryValidityVerified': False,
            'components': {ext: {'bytes': len(data), 'sha256': digest(data)}
                           for ext, data in sorted(components.items())}}


def inspect_tile(payload):
    layers = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive_members(archive)
        for name, entry in entries:
            match = COMPONENT_PATTERN.fullmatch(name)
            if match is None:
                raise TopographyDataError('알 수 없는 도엽 구성 파일')
            layer, extension = match.groups()
            layers.setdefault(layer, {})[extension] = read_member(archive, entry)
    return [inspect_layer(layer, components) for layer, components in sorted(layers.items())], sum(
        len(data) for components in layers.values() for data in components.values())


def record_id(tile, layer, record_number, tile_sha256):
    if (not re.fullmatch(r'\d{9}', tile) or not re.fullmatch(LAYER_PATTERN, layer)
            or type(record_number) is not int or record_number < 1
            or not HASH_PATTERN.fullmatch(tile_sha256)):
        raise TopographyDataError('원본 레코드 식별 입력 오류')
    return f'ngii:{tile}:{layer}:{record_number}:{tile_sha256}'


def create_catalog(connection):
    connection.executescript('''
        PRAGMA foreign_keys=ON;
        PRAGMA page_size=4096;
        PRAGMA user_version=1;
        CREATE TABLE tiles(tile TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL)
            WITHOUT ROWID;
        CREATE TABLE tile_sources(tile TEXT NOT NULL REFERENCES tiles(tile), district TEXT NOT NULL,
            package_sha256 TEXT NOT NULL, member TEXT NOT NULL, PRIMARY KEY(tile,district)) WITHOUT ROWID;
        CREATE TABLE layers(tile TEXT NOT NULL REFERENCES tiles(tile), layer TEXT NOT NULL,
            metadata TEXT NOT NULL, PRIMARY KEY(tile,layer)) WITHOUT ROWID;
    ''')


def build(manifest_path, output, root=ROOT, progress=None):
    if os.path.lexists(output):
        raise TopographyDataError('기존 출력 덮어쓰기 금지')
    if output.parent.resolve() != output.parent.absolute():
        raise TopographyDataError('출력 상위 경로의 링크 금지')
    with source_stream(manifest_path, limit=1024**2) as (stream, manifest_sha256):
        manifest = json.load(stream)
    files = manifest.get('files', [])
    if manifest.get('schemaVersion') != 1 or not 2 <= len(files) <= 64:
        raise TopographyDataError('원본 목록 구조 오류')
    packages = sorted((f for f in files if f['role'] == 'DISTRICT_TILE_PACKAGE'), key=lambda f: f['district'])
    if (not packages or len({f['district'] for f in packages}) != len(packages)
            or len({f['localPath'] for f in files}) != len(files)
            or any(f['role'] not in ('DISTRICT_TILE_PACKAGE', 'LAYER_CODE_REFERENCE') for f in files)):
        raise TopographyDataError('원본 목록 종류·중복 오류')
    for source in files:
        if (type(source['bytes']) is not int or source['bytes'] < 1
                or not HASH_PATTERN.fullmatch(source['sha256'])):
            raise TopographyDataError('원본 크기·해시 정의 오류')
        project_path(root, source['localPath'])
    output.mkdir(mode=0o700)
    try:
        (output / 'tiles').mkdir(mode=0o700)
        with closing(sqlite3.connect(output / 'catalog.sqlite')) as connection:
            create_catalog(connection)
            seen, counts, layer_counts = {}, Counter(), Counter()
            for source in files:
                if source['role'] == 'LAYER_CODE_REFERENCE':
                    with source_stream(project_path(root, source['localPath']), source['bytes'], source['sha256']):
                        pass
            for source in packages:
                path = project_path(root, source['localPath'])
                package_tiles = 0
                with source_stream(path, source['bytes'], source['sha256']) as (stream, _):
                    with zipfile.ZipFile(stream) as archive:
                        for member, entry in archive_members(archive):
                            if not re.fullmatch(r'\d{9}\.zip', member):
                                raise TopographyDataError('도엽 ZIP 이름 오류')
                            tile = member[:-4]
                            payload = read_member(archive, entry)
                            checksum = digest(payload)
                            if tile in seen and seen[tile] != checksum:
                                raise TopographyDataError('같은 도엽 ID의 다른 원본 해시 충돌')
                            if tile not in seen:
                                if len(seen) >= MAX_TILES:
                                    raise TopographyDataError('고유 도엽 수 제한 초과')
                                layers, expanded_bytes = inspect_tile(payload)
                                counts['expandedBytes'] += expanded_bytes
                                if counts['expandedBytes'] > MAX_TOTAL_BYTES:
                                    raise TopographyDataError('전체 도엽 해제 크기 제한 초과')
                                with (output / 'tiles' / member).open('xb') as target:
                                    target.write(payload)
                                seen[tile] = checksum
                                connection.execute('INSERT INTO tiles VALUES(?,?,?)', (tile, checksum, len(payload)))
                                for layer in layers:
                                    connection.execute('INSERT INTO layers VALUES(?,?,?)', (tile, layer['layer'], canonical(layer)))
                                    layer_counts[layer['layer']] += 1
                                    counts['rawRecords'] += layer['dbf']['recordCount']
                                    counts['deletedRecords'] += layer['dbf']['deletedRecordCount']
                                    counts['nullShapes'] += layer['nullShapeCount']
                                    mismatches = layer['dbf']['encodingDeclarationMismatchRecords']
                                    counts['encodingDeclarationMismatchLayers'] += mismatches > 0
                                    counts['encodingDeclarationMismatchRecords'] += mismatches
                            else:
                                counts['repeatedTileReferences'] += 1
                            connection.execute('INSERT INTO tile_sources VALUES(?,?,?,?)',
                                (tile, source['district'], source['sha256'], member))
                            package_tiles += 1
                if package_tiles != source['tileZipCount']:
                    raise TopographyDataError('등록 구별 도엽 수 불일치')
                counts['tileReferences'] += package_tiles
                if progress:
                    progress(source['district'], len(seen))
            counts['uniqueTileCount'] = len(seen)
            for key in ('tileReferences', 'uniqueTileCount', 'repeatedTileReferences'):
                if counts[key] != manifest['inventory'][key]:
                    raise TopographyDataError('등록 전체 도엽 수 불일치')
            connection.commit()
            connection.execute('VACUUM')
            if connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise TopographyDataError('카탈로그 무결성 검사 실패')
        with (output / 'catalog.sqlite').open('rb') as stream:
            catalog_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        summary = {'schemaVersion': 1, 'status': 'VERIFIED_SOURCE_CATALOG_NOT_SERVICE_MIGRATED',
            'manifestSha256': manifest_sha256, 'generatorSha256': digest(Path(__file__).read_bytes()),
            'distributionUpdatedAt': manifest['distributionUpdatedAt'], 'nativeCrs': 'EPSG:5186',
            'catalogSha256': catalog_sha256, 'packageCount': len(packages), 'layerTypeCount': len(layer_counts),
            'layerInstanceCount': sum(layer_counts.values()), 'counts': dict(sorted(counts.items())),
            'layerTileCounts': dict(sorted(layer_counts.items())), 'recordId': 'ngii:{tile}:{layer}:{1-based-record-number}:{tile-sha256}',
            'checks': {'allRegisteredFileHashes': True, 'archivePathsSizesCrc': True,
                'shapeIndexDbfRecordAlignment': True, 'allLayerCrs': True, 'strictDbfDecoding': True,
                'geometryValidity': False, 'seoulCoverage': False, 'fieldAccuracy': False, 'serviceMigration': False},
            'versions': {'python': '.'.join(map(str, sys.version_info[:3])), 'sqlite': sqlite3.sqlite_version,
                         'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str}}
        with (output / 'summary.json').open('x', encoding='utf-8') as target:
            target.write(canonical(summary) + '\n')
        return summary
    except BaseException:
        # 완료 표식이 없는 부분 산출물을 다음 실행이 정상 카탈로그로 읽지 않게 한다.
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / MANIFEST)
    parser.add_argument('--output', type=Path, default=ROOT / OUTPUT)
    args = parser.parse_args()
    try:
        pyproj.network.set_network_enabled(False)
        summary = build(args.manifest, args.output.absolute(), progress=lambda district, count:
                        print(f'{district}: 고유 도엽 {count}', flush=True))
    except TopographyDataError as exc:
        parser.exit(1, f'수치지형도 검증 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile, zlib.error, sqlite3.DatabaseError):
        parser.exit(1, '수치지형도 검증 실패: 원본·압축 구성·좌표계·목록 확인 필요\n')
    print(canonical({'status': summary['status'], 'counts': summary['counts'], 'catalogSha256': summary['catalogSha256']}))


if __name__ == '__main__':
    main()
