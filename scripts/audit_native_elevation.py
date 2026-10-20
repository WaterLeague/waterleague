"""원 등고선·표고점 분포와 미확인 높이 기준 검사. 표시/수문 지형 생성 없음."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3

import pyproj

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {'N1L_F0010000': '등고수치', 'N1P_F0020000': '수치',
          'N3L_F0010000': '등고수치', 'N3P_F0020000': '수치'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            value.update(block)
    return value.hexdigest()


def audit():
    manifest_path = ROOT / 'data/manifests/seoul-spatial-catalog-v1.json'
    manifest_sha = digest(manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    database = ROOT / 'data/private/vworld-seoul-topography-20260307/spatial-v1/spatial.sqlite'
    code_sha = digest(Path(__file__))
    if database.is_symlink() or digest(database) != manifest['spatialSha256']:
        raise ValueError('원 공간 입력 해시 불일치')
    values, tiles, grids = defaultdict(list), defaultdict(Counter), defaultdict(Counter)
    wkts, shapes = set(), set()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        for layer, metadata in db.execute('SELECT layer,metadata FROM layers WHERE layer IN (?,?,?,?)', tuple(LAYERS)):
            value = json.loads(metadata)
            if value['nativeCrs'] != 'EPSG:5186':
                raise ValueError('표고 레이어의 수평 좌표계 불일치')
            wkts.add(value['originalWkt'])
            shapes.add(value['shapeType'])
        for layer, tile, properties, status, minx, miny, maxx, maxy in db.execute(
                'SELECT layer,tile,properties,geometry_status,minx,miny,maxx,maxy FROM features '
                'WHERE layer IN (?,?,?,?) AND deleted=0 ORDER BY fid', tuple(LAYERS)):
            number = Decimal(json.loads(properties)[LAYERS[layer]])
            if status != 'VALID' or not number.is_finite() or not all(math.isfinite(n) for n in (minx, miny, maxx, maxy)):
                raise ValueError('표고 원문·도형·좌표 오류')
            values[layer].append(number)
            tiles[tile][layer] += 1
            grid = f'{math.floor((minx + maxx) / 10000)}_{math.floor((miny + maxy) / 10000)}'
            grids[grid][layer] += 1
    crs_reports = []
    if set(values) != set(LAYERS) or not wkts:
        raise ValueError('필수 표고 레이어 누락')
    for wkt in sorted(wkts):
        crs = pyproj.CRS.from_wkt(wkt)
        if crs.to_authority() != ('EPSG', '5186') or crs.is_vertical or any(axis.unit_name != 'metre' for axis in crs.axis_info):
            raise ValueError('수평 좌표계·축 단위 불일치')
        crs_reports.append({'wktSha256': hashlib.sha256(wkt.encode()).hexdigest(),
            'horizontalCrs': 'EPSG:5186', 'horizontalUnit': 'metre',
            'verticalCrsDeclared': False, 'axisCount': len(crs.axis_info)})
    summary = {}
    for layer, numbers in values.items():
        numbers.sort()
        if len(numbers) != manifest['layerCounts'][layer]['records']:
            raise ValueError('원 표고 집계 누락')
        summary[layer] = {'records': len(numbers), 'nonemptySourceTiles': sum(layer in value for value in tiles.values()),
            'attribute': LAYERS[layer], 'minimumRawNumeric': str(numbers[0]), 'maximumRawNumeric': str(numbers[-1]),
            'negativeRecords': sum(n < 0 for n in numbers), 'zeroRecords': numbers.count(0),
            'rawOrderStatistics': {str(p): str(numbers[math.floor((len(numbers) - 1) * p)]) for p in (0.1, 0.5, 0.9)},
            'orderStatisticIndexPolicy': 'FLOOR((N-1)*P)',
            'attributeUnit': 'NOT_CONFIRMED_BY_CODE_MANUAL', 'verticalDatum': None}
    if (digest(database) != manifest['spatialSha256'] or digest(Path(__file__)) != code_sha
            or digest(manifest_path) != manifest_sha):
        raise ValueError('검사 중 입력·코드 변경')
    return {'schemaVersion': 1, 'status': 'AUDITED_NOT_HYDROLOGIC_TERRAIN',
        'generatorSha256': code_sha, 'sourceSpatialSha256': manifest['spatialSha256'],
        'sourceManifestSha256': manifest_sha, 'sourceShapeTypes': sorted(shapes),
        'horizontalCrsChecks': crs_reports, 'layers': summary,
        'sourceTileCounts': {k: dict(v) for k, v in sorted(tiles.items())},
        'projectedBboxCenterGridCounts': {k: dict(v) for k, v in sorted(grids.items())},
        'gridSizeM': 5000, 'gridMethod': 'SOURCE_GEOMETRY_BOUNDING_BOX_CENTER_NOT_DRAINAGE_AREA',
        'recordCountsAreUniqueAssets': False, 'ngiiVerticalDatumConfirmed': False,
        'heightAttributeUnitsConfirmed': False, 'interpolatedTerrainCreated': False,
        'usedAsSiteSlopeOrHydrologicTerrain': False, 'fieldAccuracyVerified': False,
        'versions': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                     'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.report.is_symlink():
        parser.error('기존 검사 결과 덮어쓰기 금지')
    report = audit()
    with args.report.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'records': sum(v['records'] for v in report['layers'].values())}))


if __name__ == '__main__':
    main()
