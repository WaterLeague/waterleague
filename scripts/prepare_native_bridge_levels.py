"""원 교량의 레코드 결속과 공개 복층 관계에 따른 표시 상판 보완."""
import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3

import shapely
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import substring

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_objects import object_key
from prepare_native_street_life import walk_paths

BASE = source.ROOT / 'data/private/vworld-seoul-topography-20260307/spatial-v1'
SOURCES = {
    '반포대교': 'https://news.seoul.go.kr/env/archives/520397',
    '청담대교': 'https://news.seoul.go.kr/citybuild/archives/208956',
}


def parts(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [part for child in getattr(geometry, 'geoms', []) for part in parts(child, kind)]


def polygons(geometry):
    return [mapping(p)['coordinates'] for p in parts(geometry, 'Polygon') if p.area > .01]


def build(input_dir, output):
    if output.exists() or output.is_symlink():
        raise ValueError('기존 교량 묶음 덮어쓰기 금지')
    index_raw = (input_dir / 'index.json').read_bytes()
    index = json.loads(index_raw)
    packed = (input_dir / index['file']).read_bytes()
    raw = gzip.decompress(packed)
    if source.digest(raw) != index['sha256'] or source.digest(packed) != index['storedSha256']:
        raise ValueError('입력 교량 해시 불일치')
    if spatial.file_sha256(BASE / 'spatial.sqlite') != index['sourceSpatialSha256']:
        raise ValueError('원 공간 자료 해시 불일치')
    body = json.loads(raw)
    wanted = {s['sourceId'] for g in body['groups'] for s in g.get('sidewalks', [])}
    wanted.update(r.split(':part:')[0] for g in body['groups'] for p in g['profiles'] for r in p['roadIds'])
    fids = defaultdict(list)
    with closing(sqlite3.connect('file:' + str(BASE / 'spatial.sqlite') + '?mode=ro&immutable=1', uri=True)) as db:
        for fid, layer, wkb in db.execute("SELECT fid,layer,geometry_wkb FROM features WHERE layer IN ('N1L_A0020000','N1L_A0150000','N1A_A0033320') AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            key = object_key(layer, shapely.from_wkb(wkb))
            if key in wanted:
                fids[key].append(fid)
    if wanted - fids.keys():
        raise ValueError('교량 교통 원본 레코드 대응 누락')
    levels = []
    for group in body['groups']:
        for profile in group['profiles']:
            profile['sourceFids'] = sorted({fid for rid in profile['roadIds'] for fid in fids[rid.split(':part:')[0]]})
        for sidewalk in group.get('sidewalks', []):
            sidewalk['sourceFids'] = fids[sidewalk['sourceId']]
        names = group.get('names', [])
        if group['role'] != 'BRIDGE_AREA' or not names or names[0] not in SOURCES:
            continue
        candidates = [p for p in group['profiles'] if not p.get('rail') and not p.get('steps')]
        if not candidates:
            raise ValueError('복층 교량 원 중심선 누락')
        profile = max(candidates, key=lambda p: p['span'][1] - p['span'][0])
        if profile['span'][1] - profile['span'][0] < 500:
            continue
        rail = names[0] == '청담대교'
        width = 10 if rail else 18
        outline = shapely.union_all([Polygon(p[0], p[1:]) for p in group['polygons']])
        path = LineString(profile['coordinates'])
        selected = [p for p in candidates if p['displayWidthM'] >= width]
        main = shapely.union_all([substring(LineString(p['coordinates']), *p['span']) for p in selected])
        # 하층 원본 외곽이 없어 원 중심선의 표시 폭을 원 교량 외곽으로 제한한다.
        surface = main.buffer(width / 2, cap_style='flat', join_style='mitre').intersection(outline)
        sidewalk = surface.difference(main.buffer(width / 2 - 2, cap_style='flat', join_style='mitre')) if not rail else Polygon()
        approaches = []
        seen_approaches = Polygon()
        if not rail:
            for p in selected:
                approach = shapely.union_all([Polygon(q[0], q[1:]) for q in p['polygons']]).intersection(LineString(p['coordinates']).buffer(width / 2, cap_style='flat', join_style='mitre')).difference(seen_approaches)
                if polygons(approach):
                    approaches.append({**p, 'polygons': polygons(approach)})
                    seen_approaches = shapely.union_all([seen_approaches, approach])
        tracks = []
        if rail:
            for offset in [-2, 2]:
                for line in parts(main.offset_curve(offset).intersection(surface), 'LineString'):
                    tracks.append(list(line.coords))
        group['lowerDeck'] = dict(
            name='청담대교 하부 전철' if rail else '잠수교', rail=rail,
            displayOnly=True, geometryBasis='SOURCE_AXIS_CLIPPED_TO_SOURCE_BRIDGE',
            sourceUrl=SOURCES[names[0]], displayWidthM=width, deckLiftM=6.5,
            polygons=polygons(surface), sidewalks=polygons(sidewalk),
            walkPaths=[list(p.coords) for p in walk_paths(sidewalk)] if not rail else [],
            railPaths=tracks,
            approaches=approaches,
        )
        assert surface.difference(outline).area < .001
        assert sidewalk.difference(surface).area < .001
        levels.append(dict(name=group['lowerDeck']['name'], sourceId=group['id'], areaM2=surface.area,
                           sidewalkAreaM2=sidewalk.area, railPaths=len(tracks)))
    if len(levels) != 2:
        raise ValueError('반포·청담 하층 대응 개수 오류')
    output.mkdir()
    raw = (source.canonical(body) + '\n').encode()
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    (output / index['file']).write_bytes(packed)
    index.update(sha256=source.digest(raw), bytes=len(raw), storedSha256=source.digest(packed), storedBytes=len(packed))
    index['levelSupplement'] = dict(generatorSha256=spatial.file_sha256(__file__),
        sourceBridgeIndexSha256=source.digest(index_raw), sourceUrls=SOURCES, lowerDecks=levels,
        geometryIsDisplayAssumption=True, upperLiftM=13.5, lowerLiftM=6.5,
        banpoWidthSource='SEOUL_PUBLISHED_18M', cheongdamWidthSource='DISPLAY_ASSUMPTION_10M',
        lowerApproachSource='BANPO_EXISTING_ROAD_APPROACH_PROJECTION',
        railAlignmentSource='CHEONGDAM_UPPER_ROAD_AXIS_PROJECTION',
        sourceBoundObjects=len(fids), hydraulicInputsChanged=False)
    (output / 'index.json').write_text(source.canonical(index) + '\n')
    print(source.canonical(dict(indexSha256=spatial.file_sha256(output / 'index.json'), sourceBoundObjects=len(fids), lowerDecks=levels)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=source.ROOT / 'frontend/public/data/seoul-bridges-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.input.absolute(), args.output.absolute())
