"""공개 도로와 좌표계 후보의 일치도를 보존하는 관망 위치 가정."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
from urllib.parse import quote

import pyproj
from pyproj import CRS, Transformer, database, network
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from topography_catalog import SpatialCatalog

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT/'backend/src/main/resources/watersheds/seocho-layout-v1.json'
SOURCE = ROOT/'data/manifests/seoul-spatial-catalog-v1.json'
CANDIDATES = (2097, 5174, 5181, 5186)
SELECTED = 5181
BUFFER = 200.0
SPACING = 10.0
LAYER = 'N1L_A0020000'
METHOD = 'ROAD_SUPPORTED_CRS_HYPOTHESIS_V1'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                       allow_nan=False)+'\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def transform_layout(layout, code):
    if (layout.get('classification') != 'PUBLISHED_MODEL_COORDINATES_NOT_GEOREFERENCED'
            or layout.get('horizontalCrs') is not None or code not in CANDIDATES):
        raise ValueError('원 좌표 분류·후보 오류')
    transformer = Transformer.from_crs(code, 5186, always_xy=True, allow_ballpark=False, only_best=True)

    def point(p):
        if len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p):
            raise ValueError('원 좌표 오류')
        result = list(transformer.transform(*p, errcheck=True))
        if not all(math.isfinite(v) for v in result):
            raise ValueError('변환 좌표 오류')
        return result

    result = {'nodes': [{**r, 'coordinate': point(r['coordinate'])} for r in layout['nodes']]}
    for key in ('links', 'catchments'):
        result[key] = [{**r, 'points': [point(p) for p in r['points']]} for r in layout[key]]
    operation = transformer.get_last_used_operation() if code != 5186 else transformer
    return result, {'sourceCrs': f'EPSG:{code}', 'sourceWkt': CRS(code).to_wkt(),
                    'targetCrs': 'EPSG:5186', 'axisOrder': 'x=easting,y=northing',
                    'alwaysXY': True, 'allowBallpark': False, 'onlyBest': True,
                    'definition': operation.definition, 'description': operation.description,
                    'declaredOperationAccuracyM': operation.accuracy}


def extent(layout):
    points = [n['coordinate'] for n in layout['nodes']]
    points += [p for k in ('links', 'catchments') for r in layout[k] for p in r['points']]
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def samples(layout):
    rows = [{'kind': n['kind'], 'id': n['id'], 'point': n['coordinate'], 'weightM': None}
            for n in layout['nodes']]
    for link in layout['links']:
        line = LineString(link['points'])
        if not line.is_valid or line.length <= 0:
            raise ValueError('관로 표시선 오류')
        count = math.ceil(line.length/SPACING)
        for i in range(count):
            at = (i+.5)*line.length/count
            rows.append({'kind': 'CONDUIT_MIDPOINT', 'id': link['id'], 'sample': i,
                         'distanceAlongM': at, 'point': list(line.interpolate(at).coords[0]),
                         'weightM': line.length/count})
    return rows


def nearest_samples(points, roads):
    roads = sorted(roads, key=lambda r: r['id'])
    tree = STRtree([r['geometry'] for r in roads])
    result = []
    for row in points:
        point = Point(row['point'])
        # 조회 여유 밖의 도로를 실제 최근접 도로로 확정하지 않는다.
        indexes, distances = tree.query_nearest(point, max_distance=BUFFER, return_distance=True)
        nearest = min((int(i) for i in indexes), key=lambda i: roads[i]['id'], default=None)
        if nearest is None:
            result.append({**row, 'distanceM': None, 'roadId': None, 'equidistantRoadCount': 0})
        else:
            road = roads[nearest]
            result.append({**row, 'distanceM': float(min(distances)), 'roadId': road['id'],
                           'equidistantRoadCount': len(indexes)})
    return result


def summarize(rows):
    values = [r['distanceM'] for r in rows if r['distanceM'] is not None]
    complete = len(values) == len(rows) and bool(rows)
    weighted = complete and all(r['weightM'] is not None for r in rows)
    return {'sampleCount': len(rows), 'coveredCount': len(values), 'complete': complete,
            'meanM': statistics.fmean(values) if complete else None,
            'medianM': statistics.median(values) if complete else None,
            'maxM': max(values) if complete else None,
            'lengthWeightedMeanM': (math.fsum(r['distanceM']*r['weightM'] for r in rows)
                                   /math.fsum(r['weightM'] for r in rows)) if weighted else None}


def excluded_roads(spatial, bounds):
    uri = 'file:'+quote(str(spatial.database))+'?mode=ro&immutable=1'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute('PRAGMA trusted_schema=OFF')
        rows = connection.execute('''SELECT tile,layer,record_number,geometry_status,
            geometry_detail,deleted,raw_shape_sha256,raw_dbf_sha256 FROM features
            WHERE layer=? AND (geometry_status!='VALID' OR deleted!=0)
            AND (minx IS NULL OR (maxx>=? AND minx<=? AND maxy>=? AND miny<=?))
            ORDER BY tile,record_number''', (LAYER, bounds[0], bounds[2], bounds[1], bounds[3])).fetchall()
    return [dict(zip(('tile', 'layer', 'recordNumber', 'geometryStatus', 'geometryDetail',
                      'deleted', 'sourceShapeSha256', 'sourceDbfSha256'), row, strict=True)) for row in rows]


def audit(layout, spatial):
    candidates = []
    layouts = {}
    for code in CANDIDATES:
        projected, operation = transform_layout(layout, code)
        box = extent(projected)
        bounds = [box[0]-BUFFER, box[1]-BUFFER, box[2]+BUFFER, box[3]+BUFFER]
        roads = spatial.query(bounds, layers=[LAYER])
        rows = nearest_samples(samples(projected), roads)
        excluded = excluded_roads(spatial, bounds)
        candidates.append({'sourceCrsHypothesis': f'EPSG:{code}', 'operation': operation,
                           'queryBounds': bounds, 'roadCount': len(roads), 'excludedRoads': excluded,
                           'nodes': summarize([r for r in rows if r['weightM'] is None]),
                           'conduits': summarize([r for r in rows if r['weightM'] is not None]),
                           'samples': rows,
                           'roads': [{k: r[k] for k in ('id', 'sourceShapeSha256', 'sourceDbfSha256')}
                                     for r in sorted(roads, key=lambda r: r['id'])]})
        layouts[code] = projected
    selected = next(c for c in candidates if c['sourceCrsHypothesis'] == f'EPSG:{SELECTED}')
    # 미리 정한 가정의 근거가 바뀌면 다른 후보를 자동 선택하지 않는다.
    if (not selected['nodes']['complete'] or not selected['conduits']['complete']
            or selected['excludedRoads']
            or any(c['nodes']['complete'] and c != selected
                   and (c['nodes']['meanM'] <= selected['nodes']['meanM']
                        or c['conduits']['lengthWeightedMeanM'] is None
                        or c['conduits']['lengthWeightedMeanM'] <= selected['conduits']['lengthWeightedMeanM'])
                   for c in candidates)):
        raise ValueError('명시한 좌표계 가정의 비교 근거 재검토 필요')
    return candidates, layouts[SELECTED]


def write_fixed(path, raw):
    path = Path(path)
    if path.is_symlink() or path.exists() and path.read_bytes() != raw:
        raise ValueError('기존 파생 근거 덮어쓰기 금지')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    args = parser.parse_args()
    network.set_network_enabled(False)
    raw = LAYOUT.read_bytes()
    layout = json.loads(raw)
    source = json.loads(SOURCE.read_bytes())
    spatial = SpatialCatalog(ROOT/source['localCatalogDirectory'], source)
    candidates, projected = audit(layout, spatial)
    common = {'schemaVersion': 1, 'method': METHOD, 'sourceLayoutSha256': digest(raw),
              'sourceOriginalSha256': layout['sourceOriginalSha256'], 'sourceUrl': layout['sourceUrl'],
              'sourceCrsVerified': False, 'assumedSourceCrs': f'EPSG:{SELECTED}',
              'horizontalCrs': 'EPSG:5186', 'verticalDatum': None,
              'roadSource': {k: source[k] for k in ('spatialSha256', 'sourceManifestSha256',
                  'sourceCatalogSha256', 'semanticsSha256', 'distributionUpdatedAt')},
              'basis': 'https://doi.org/10.1016/j.jenvman.2024.122344',
              'basisSection': '3.1–3.2: road-network-based drainage/catchments',
              'scope': 'PUBLISHED_RESEARCH_MODEL_LOCATION_ASSUMPTION',
              'rankingEligible': False, 'historicalReconstructionEligible': False,
              'limitations': ['EPSG:5181은 공개 도로와의 일치도에 근거한 위치 가정; 저자 확인 좌표계 아님',
                  '2026년 공개 도로와 비교; 출판 시점·2010년 현장 관망 위치 검증 아님',
                  '집수구역 선택은 면적 배분이며 개별 시설 부지·지표 유입구의 확정 위치가 아님',
                  '원 관망의 높이·외부 유입·강우·제원은 변환하지 않으며 지표 결합과 순위 자격은 별도']}
    evidence = {**common, 'generatorSha256': digest(Path(__file__).read_bytes()),
                'spatialReaderSha256': digest((ROOT/'scripts/topography_catalog.py').read_bytes()),
                'versions': {'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                             'epsg': database.get_database_metadata('EPSG.VERSION'),
                             'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
                'comparison': {'candidateCodes': list(CANDIDATES), 'roadLayer': LAYER,
                               'bufferM': BUFFER, 'conduitMaxSegmentM': SPACING,
                               'fittedTranslation': False, 'snapping': False, 'outlierRemoval': False},
                'candidates': candidates}
    evidence_raw = encode(evidence)
    selected = next(c for c in candidates if c['sourceCrsHypothesis'] == common['assumedSourceCrs'])
    profile = {**common, 'id': 'SEOCHO_ROAD_SUPPORTED_LOCATION_V1',
               'evidenceSha256': digest(evidence_raw), 'bounds': extent(projected),
               'comparison': [{k: c[k] for k in ('sourceCrsHypothesis', 'roadCount', 'nodes', 'conduits')}
                              for c in candidates], 'operation': selected['operation'], **projected}
    write_fixed(args.evidence, evidence_raw)
    write_fixed(args.profile, encode(profile))
    print(json.dumps({'profileSha256': digest(encode(profile)), 'evidenceSha256': digest(evidence_raw),
                      'comparison': profile['comparison']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
