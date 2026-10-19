"""검증된 수치지형도 카탈로그의 원 레코드·미터 도형·코드 해석."""
from contextlib import closing
from decimal import Decimal, InvalidOperation
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
from urllib.parse import quote
import zipfile

import shapely
from shapely.geometry import LineString, LinearRing, MultiLineString, MultiPolygon, Point, Polygon, box

import prepare_seoul_topography as source

SEMANTICS_PATH = source.ROOT / 'data/manifests/seoul-topography-semantics-v1.json'


def read_json(path, limit=1024**2):
    with source.source_stream(path, limit=limit) as (stream, _):
        return json.load(stream)


class SourceCatalog:
    def __init__(self, directory, expected, semantics=None):
        self.directory = Path(directory).absolute()
        if self.directory.resolve() != self.directory:
            raise source.TopographyDataError('입력 카탈로그 경로의 링크 금지')
        self.summary = read_json(self.directory / 'summary.json')
        for key in ('catalogSha256', 'manifestSha256', 'generatorSha256', 'schemaVersion', 'status'):
            if self.summary[key] != expected[key]:
                raise source.TopographyDataError('공개 입력 카탈로그 요약 불일치')
        if semantics is None:
            with source.source_stream(SEMANTICS_PATH) as (stream, checksum):
                self.semantics = json.load(stream)
                self.semantics_sha256 = checksum
                self.semantics_from_file = True
        else:
            self.semantics = semantics
            self.semantics_sha256 = source.digest(source.canonical(semantics).encode())
            self.semantics_from_file = False
        self.semantics_content_sha256 = source.digest(source.canonical(self.semantics).encode())
        self.database = self.directory / 'catalog.sqlite'
        with source.source_stream(self.database, expected_sha256=expected['catalogSha256'], limit=2 * 1024**3):
            pass

    def verify_snapshot(self):
        with source.source_stream(self.database, expected_sha256=self.summary['catalogSha256'], limit=2 * 1024**3):
            pass
        if source.digest(source.canonical(self.semantics).encode()) != self.semantics_content_sha256:
            raise source.TopographyDataError('정규화 중 레이어 해석 계약 변경')
        if self.semantics_from_file:
            with source.source_stream(SEMANTICS_PATH, expected_sha256=self.semantics_sha256):
                pass

    def connect(self):
        connection = sqlite3.connect('file:' + quote(str(self.database)) + '?mode=ro&immutable=1', uri=True)
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        return connection

    def tiles(self):
        with closing(self.connect()) as connection:
            return connection.execute('SELECT tile,sha256,bytes FROM tiles ORDER BY tile').fetchall()

    def layers(self, tile, selected=None):
        if not re.fullmatch(r'\d{9}', tile):
            raise source.TopographyDataError('도엽 식별자 오류')
        with closing(self.connect()) as connection:
            entry = connection.execute('SELECT sha256,bytes FROM tiles WHERE tile=?', (tile,)).fetchone()
            rows = connection.execute('SELECT layer,metadata FROM layers WHERE tile=? ORDER BY layer', (tile,)).fetchall()
        if entry is None:
            raise source.TopographyDataError('등록되지 않은 도엽')
        checksum, size = entry
        with source.source_stream(self.directory / 'tiles' / (tile + '.zip'), size, checksum) as (stream, _):
            payload = stream.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = dict(source.archive_members(archive))
            for layer, encoded in rows:
                if selected is not None and layer not in selected:
                    continue
                metadata = json.loads(encoded)
                if layer not in self.semantics['layers']:
                    raise source.TopographyDataError('레이어 해석 계약 누락')
                components = {}
                for extension, reference in metadata['components'].items():
                    name = layer + '.' + extension
                    if name not in entries:
                        raise source.TopographyDataError('도엽 구성 누락')
                    data = source.read_member(archive, entries[name])
                    if len(data) != reference['bytes'] or source.digest(data) != reference['sha256']:
                        raise source.TopographyDataError('도엽 구성 해시 불일치')
                    components[extension] = data
                yield layer, checksum, metadata, components


class SpatialCatalog:
    def __init__(self, directory, expected):
        self.directory = Path(directory).absolute()
        if self.directory.resolve() != self.directory:
            raise source.TopographyDataError('공간 카탈로그 경로의 링크 금지')
        self.summary = read_json(self.directory / 'summary.json')
        for key in ('schemaVersion', 'status', 'spatialSha256', 'sourceCatalogSha256', 'semanticsSha256'):
            if self.summary[key] != expected[key]:
                raise source.TopographyDataError('공간 카탈로그 공개 요약 불일치')
        self.database = self.directory / 'spatial.sqlite'
        with source.source_stream(self.database, expected_sha256=expected['spatialSha256'], limit=16 * 1024**3):
            pass

    def query(self, bounds, layers=None, limit=20_000):
        if (len(bounds) != 4 or not all(math.isfinite(v) for v in bounds)
                or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]
                or type(limit) is not int or not 1 <= limit <= 20_000):
            raise source.TopographyDataError('공간 조회 범위·한도 오류')
        if layers is not None and (not 1 <= len(layers) <= 121 or
                any(not re.fullmatch(source.LAYER_PATTERN, layer) for layer in layers)):
            raise source.TopographyDataError('공간 조회 레이어 오류')
        sql = '''SELECT f.tile,f.layer,f.record_number,t.sha256,f.properties,f.geometry_wkb,
            f.raw_shape_sha256,f.raw_dbf_sha256,f.area_m2,f.length_m,l.role,l.scale_denominator
            FROM feature_bounds b CROSS JOIN features f ON f.fid=b.fid
            CROSS JOIN tiles t ON t.tile=f.tile CROSS JOIN layers l ON l.tile=f.tile AND l.layer=f.layer
            WHERE b.maxx>=? AND b.minx<=? AND b.maxy>=? AND b.miny<=?
            AND f.geometry_status='VALID' AND f.deleted=0'''
        arguments = [bounds[0], bounds[2], bounds[1], bounds[3]]
        if layers is not None:
            sql += ' AND f.layer IN (' + ','.join('?' for _ in layers) + ')'
            arguments.extend(sorted(layers))
        sql += ' ORDER BY f.tile,f.layer,f.record_number LIMIT ?'
        arguments.append(limit + 1)
        with closing(sqlite3.connect('file:' + quote(str(self.database)) + '?mode=ro&immutable=1', uri=True)) as connection:
            connection.execute('PRAGMA trusted_schema=OFF')
            rows = connection.execute(sql, arguments).fetchall()
        if len(rows) > limit:
            raise source.TopographyDataError('공간 조회 범위 축소 필요')
        boundary, result = box(*bounds), []
        for tile, layer, number, tile_sha, props, wkb, shape_sha, dbf_sha, area, length, role, scale in rows:
            geometry = shapely.from_wkb(wkb)
            if geometry.intersects(boundary):
                result.append({'id': source.record_id(tile, layer, number, tile_sha), 'geometry': geometry,
                    'areaM2': area, 'lengthM': length, 'attributes': json.loads(props), 'role': role,
                    'scaleDenominator': scale, 'sourceShapeSha256': shape_sha, 'sourceDbfSha256': dbf_sha,
                    'spatialCatalogSha256': self.summary['spatialSha256']})
        return result


def attributes(row, schema):
    result = {}
    for field in schema['fields']:
        start = field['offset']
        raw = row[start:start + field['width']]
        text = raw.decode('cp949' if field['type'] == 'C' else 'ascii', errors='strict')
        text = text.rstrip(' \0') if field['type'] == 'C' else text.strip(' \0')
        result[field['name']] = text if text else None
    return result


def records(tile, layer, tile_sha256, metadata, components):
    dbf, shp, shx = components['dbf'], components['shp'], components['shx']
    schema = metadata['dbf']
    for index in range(schema['recordCount']):
        offset, length = struct.unpack_from('>II', shx, 100 + 8 * index)
        content = shp[offset * 2 + 8:(offset + length) * 2 + 8]
        start = schema['headerBytes'] + schema['recordBytes'] * index
        row = dbf[start:start + schema['recordBytes']]
        yield {'id': source.record_id(tile, layer, index + 1, tile_sha256), 'number': index + 1,
               'rawShape': content, 'rawShapeSha256': source.digest(content),
               'rawDbfSha256': source.digest(row), 'deleted': row[0] == 42,
               'attributes': attributes(row, schema)}


def numeric_value(raw):
    if raw is None:
        return None, 'MISSING'
    if not isinstance(raw, str) or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', raw):
        return None, 'INVALID_NUMERIC_TEXT'
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, 'INVALID_NUMERIC_TEXT'
    return value, 'VALUE'


def code_meaning(raw, domain, scale=None):
    if raw is None:
        return {'status': 'MISSING', 'code': None}
    if raw in domain:
        code = raw
    else:
        codes = [key for key, value in domain.items() if value['label'] == raw]
        if len(codes) != 1:
            return {'status': 'UNKNOWN_VALUE', 'code': None}
        code = codes[0]
    entry = domain[code]
    if scale is not None and scale not in entry.get('scales', [1000, 5000, 25000]):
        return {'status': 'OUTSIDE_LISTED_SCALE', 'code': code}
    return {'status': entry['status'], 'code': code}


def native_geometry(content):
    kind = struct.unpack_from('<I', content)[0]
    geometry, part_mapping, bounds, issue = None, [], None, None
    if kind == 0:
        return {'geometry': None, 'bounds': None, 'status': 'NULL_SHAPE', 'detail': None,
                'partMapping': [], 'bboxMatches': None}
    if kind == 1:
        x, y = struct.unpack_from('<2d', content, 4)
        geometry = Point(x, y)
        bounds, declared = (x, y, x, y), (x, y, x, y)
    else:
        count, point_count = struct.unpack_from('<II', content, 36)
        indexes = list(struct.unpack_from(f'<{count}I', content, 44)) + [point_count]
        points = list(struct.iter_unpack('<2d', memoryview(content)[44 + count * 4:]))
        parts = [points[indexes[i]:indexes[i + 1]] for i in range(count)]
        bounds = (min(p[0] for p in points), min(p[1] for p in points),
                  max(p[0] for p in points), max(p[1] for p in points))
        declared = struct.unpack_from('<4d', content, 4)
        if kind == 3:
            if any(len(part) < 2 for part in parts):
                issue = 'LINE_PART_TOO_SHORT'
            else:
                geometry = LineString(parts[0]) if count == 1 else MultiLineString(parts)
                part_mapping = [[index] for index in range(count)]
        elif kind == 5:
            geometry, part_mapping, issue = polygon_parts(parts)
        else:
            raise source.TopographyDataError('지원하지 않는 원 도형 종류')
    if geometry is not None:
        if not geometry.is_valid or geometry.is_empty:
            issue = shapely.is_valid_reason(geometry)
        if issue is None and not geometry.bounds == bounds:
            raise source.TopographyDataError('원 좌표·도형 범위 보존 실패')
    return {'geometry': geometry, 'bounds': bounds, 'status': 'VALID' if issue is None else 'INVALID',
            'detail': issue, 'partMapping': part_mapping, 'bboxMatches': bounds == declared}


def polygon_parts(parts):
    # 자동 닫힘·방향 반전·복구 없이 ESRI 원 링의 외곽/구멍 의미만 해석한다.
    if any(len(ring) < 4 or ring[0] != ring[-1] for ring in parts):
        return None, [], 'UNCLOSED_OR_SHORT_RING'
    rings = [LinearRing(part) for part in parts]
    shells = [index for index, ring in enumerate(rings) if not shapely.is_ccw(ring)]
    holes = [index for index, ring in enumerate(rings) if shapely.is_ccw(ring)]
    if not shells:
        return None, [], 'NO_CLOCKWISE_SHELL'
    shell_polygons = {index: Polygon(parts[index]) for index in shells}
    if holes and any(not polygon.is_valid for polygon in shell_polygons.values()):
        return None, [], 'INVALID_SHELL_WITH_HOLES'
    assignments = {index: [] for index in shells}
    for index in holes:
        hole = Polygon(parts[index])
        if not hole.is_valid:
            return None, [], 'INVALID_HOLE'
        candidates = [shell for shell in shells if shell_polygons[shell].covers(hole)]
        if len(candidates) != 1:
            return None, [], 'HOLE_WITHOUT_UNIQUE_SHELL'
        assignments[candidates[0]].append(index)
    mapping = [[index, *assignments[index]] for index in shells]
    polygons = [Polygon(parts[index], [parts[h] for h in assignments[index]]) for index in shells]
    geometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    if shapely.get_num_coordinates(geometry) != sum(len(part) for part in parts):
        raise source.TopographyDataError('원 링 꼭짓점 보존 실패')
    return geometry, mapping, None
