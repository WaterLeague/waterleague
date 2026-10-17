"""보관된 공개 도로·녹지·수면을 계산 모델과 분리한 주변 표시 자료로 변환."""
import json
import math
import re
from collections import Counter
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import box, shape
from shapely.strtree import STRtree

from prepare_seoul_city import ROOT, SOURCE, PBF_HASH, SOURCE_URL, digest
from prepare_seoul_play_models import payload, sha, write

WIDTHS = {'motorway': 18, 'trunk': 16, 'primary': 12, 'secondary': 12, 'tertiary': 8,
          'motorway_link': 8, 'trunk_link': 8, 'primary_link': 8, 'secondary_link': 7,
          'tertiary_link': 6, 'residential': 7, 'unclassified': 7, 'living_street': 5,
          'service': 5, 'pedestrian': 4, 'footway': 2.8, 'path': 2, 'steps': 2, 'cycleway': 2.5}


def tags_of(properties):
    tags = properties.get('other_tags') or {}
    return {**(json.loads(tags) if isinstance(tags, str) else tags),
            **{k: v for k, v in properties.items() if v is not None and k != 'other_tags'}}


def above_ground(tags):
    if any(tags.get(k) not in (None, '', 'no', 'false', '0') for k in ('tunnel', 'covered')):
        return False
    if tags.get('location') in ('underground', 'underwater') or tags.get('indoor') == 'yes':
        return False
    try:
        layer = float(tags.get('layer', 0))
        return math.isfinite(layer) and layer >= 0
    except (ValueError, TypeError):
        return False


def width_of(tags, kind):
    raw = str(tags.get('width', '')).strip()
    if re.fullmatch(r'\d+(?:\.\d+)?(?: m)?', raw):
        width = float(raw.removesuffix(' m'))
        if 0 < width <= 80:
            return width, 'OSM_WIDTH_TAG'
    return (3 if kind == 'rail' else WIDTHS[tags['highway']]), 'DISPLAY_ASSUMPTION'


def polygon_parts(g):
    if g.geom_type == 'Polygon':
        return [g] if g.area > .01 else []
    return [p for child in getattr(g, 'geoms', []) for p in polygon_parts(child)]


def polygons(g, origin):
    return [[[[x-origin[0], y-origin[1]] for x, y in ring.coords]
             for ring in (p.exterior, *p.interiors)] for p in polygon_parts(g)]


def main():
    source = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_text())
    if digest(SOURCE/'south-korea-261016.osm.pbf') != PBF_HASH:
        raise ValueError('보관 원본 해시 불일치')
    for name, expected in source['extractHashes'].items():
        if digest(SOURCE/name) != expected:
            raise ValueError('추출 도형 해시 불일치')
    registry = json.loads((ROOT/'data/manifests/seoul-play-v1.json').read_text())
    maps = json.loads((ROOT/'frontend/public/data/maps.json').read_text())
    entries = {e['id']: e for e in maps['maps']}
    regions = []
    for r in registry['regions']:
        path = ROOT/'frontend/public/data'/r['mapFile']
        if digest(path) != r['mapSha256']:
            raise ValueError('기반 지도 해시 불일치')
        m = json.loads(path.read_text()); x, y = m['originProjected']
        regions.append((r, m, box(x-500, y-500, x+500, y+500)))
    forward = pyproj.Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
    backward = pyproj.Transformer.from_crs(5186, 4326, always_xy=True, allow_ballpark=False)
    project = lambda g: shapely.transform(g, forward.transform, interleaved=False)
    area = shapely.transform(shapely.union_all([r[2].buffer(100) for r in regions]), backward.transform, interleaved=False)
    features = []
    skipped = Counter()
    for f in json.loads((SOURCE/'seoul-lines.geojson').read_text())['features']:
        p = tags_of(f['properties'])
        kind = 'road' if p.get('highway') in WIDTHS else 'rail' if p.get('railway') in ('rail', 'light_rail', 'tram') else None
        if not kind:
            continue
        g = shape(f['geometry'])
        if not g.intersects(area):
            continue
        if not g.is_valid or g.is_empty or g.geom_type not in ('LineString', 'MultiLineString'):
            skipped['invalid_line'] += 1
            continue
        if not above_ground(p):
            skipped['underground_or_covered'] += 1
            continue
        width, evidence = width_of(p, kind)
        native = project(g)
        features.append({'geometry': native.buffer(width/2, quad_segs=3, cap_style='round', join_style='round'),
                         'line': native, 'id': 'way/'+p['osm_id'], 'kind': kind, 'name': p.get('name', ''),
                         'classification': p.get('highway' if kind == 'road' else 'railway'),
                         'widthM': width, 'widthEvidence': evidence,
                         'structure': 'BRIDGE' if p.get('bridge') not in (None, '', 'no', 'false', '0') else 'SURFACE',
                         'sourceTags': {k: p[k] for k in ('width', 'tunnel', 'covered', 'layer', 'location', 'indoor', 'bridge') if k in p}})
    for f in json.loads((SOURCE/'seoul-polygons.geojson').read_text())['features']:
        p = tags_of(f['properties'])
        if p.get('building') not in (None, 'no'):
            continue
        kind = ('water' if p.get('natural') == 'water' or p.get('landuse') == 'reservoir' else
                'green' if p.get('natural') in ('wood', 'scrub', 'grassland') or p.get('landuse') in
                ('forest', 'grass', 'recreation_ground') or p.get('leisure') in ('park', 'garden') else None)
        if not kind:
            continue
        g = shape(f['geometry'])
        if not g.intersects(area):
            continue
        if not g.is_valid or g.is_empty or g.geom_type not in ('Polygon', 'MultiPolygon'):
            skipped['invalid_'+kind] += 1
            continue
        if not above_ground(p):
            skipped['underground_surface'] += 1
            continue
        features.append({'geometry': project(g), 'id': ('relation/'+p['osm_id']) if p.get('osm_id') else ('way/'+p['osm_way_id']),
                         'kind': kind, 'name': p.get('name', ''),
                         'classification': p.get('natural') or p.get('landuse') or p.get('leisure'),
                         'sourceTags': {k: p[k] for k in ('natural', 'landuse', 'leisure') if k in p}})
    tree = STRtree([f['geometry'] for f in features])
    reports = []
    for region, snapshot, boundary in regions:
        origin = snapshot['originProjected']; output = []; labels = []
        for index in tree.query(boundary, predicate='intersects'):
            source_feature = features[index]
            g = source_feature['geometry'].intersection(boundary)
            if not polygon_parts(g):
                continue
            item = {k: v for k, v in source_feature.items() if k not in ('geometry', 'line')}
            item['polygons'] = polygons(g, origin)
            output.append(item)
            if item['kind'] == 'road' and item['name'] and item['classification'] in ('primary', 'secondary', 'tertiary', 'residential'):
                line = source_feature['line'].intersection(boundary)
                if line.geom_type == 'LineString' and line.length > 80:
                    point = line.interpolate(.5, normalized=True)
                    labels.append({'name': item['name'], 'center': [point.x-origin[0], point.y-origin[1]], 'length': line.length})
        chosen = []
        for label in sorted(labels, key=lambda l: (-l['length'], l['name'])):
            if all(label['name'] != other['name'] and math.dist(label['center'], other['center']) > 180 for other in chosen):
                chosen.append(label)
            if len(chosen) == 3:
                break
        counts = dict(Counter(f['kind'] for f in output))
        document = {'schemaVersion': 1, 'mapId': region['mapId'], 'baseMapSha256': region['mapSha256'],
                    'sourceSha256': PBF_HASH, 'sourceDate': '2026-10-16', 'modelInput': False,
                    'coordinateSystem': 'EPSG:5186_LOCAL_TRANSLATION', 'originProjected': origin,
                    'widthM': 1000, 'depthM': 1000, 'features': sorted(output, key=lambda f: (f['kind'], f['id'])),
                    'labels': [{k: v for k,v in l.items() if k != 'length'} for l in chosen],
                    'featureCounts': counts, 'attribution': '© OpenStreetMap contributors · Geofabrik · ODbL 1.0',
                    'limitations': ['주변 형상 표시 전용; SWMM 면적·불투수율·경사·관망 입력 아님',
                        '도로 중심선 폭 확장; 원본 폭 태그 또는 분류별 표현 가정, 현장 실측 경계 아님',
                        '지하·피복 도로 제외, 교량은 평면 투영; 실제 높이·경사 미반영',
                        '공원·녹지 경계는 실제 식생 분포나 토양 투수성의 관측 근거가 아님']}
        raw = payload(document)
        if len(raw) > 2*1024*1024:
            raise ValueError('주변 표시 자료 크기 상한 초과')
        name = 'seoul-context-v1-'+region['districtId']+'.json'
        write(ROOT/'frontend/public/data'/name, raw)
        reference = {'file': name, 'sha256': sha(raw), 'bytes': len(raw)}
        entries[region['mapId']]['context'] = reference
        reports.append({'mapId': region['mapId'], 'baseMapSha256': region['mapSha256'], **reference, 'counts': counts})
        print(region['districtName'], counts, len(raw), flush=True)
    manifest = {'schemaVersion': 1, 'sourceSha256': PBF_HASH, 'sourceUrl': SOURCE_URL,
                'extractHashes': source['extractHashes'], 'generatorSha256': digest(Path(__file__)),
                'coordinateSystem': 'EPSG:5186_LOCAL_TRANSLATION', 'displayWidthAssumptionsM': WIDTHS | {'rail': 3},
                'modelInput': False, 'excludedInSourceSelectionArea': dict(skipped), 'maps': reports}
    write(ROOT/'data/manifests/seoul-context-v1.json', payload(manifest))
    write(ROOT/'frontend/public/data/maps.json', payload(maps), mutable=True)


if __name__ == '__main__':
    main()
