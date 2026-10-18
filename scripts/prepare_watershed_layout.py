"""공개 관망의 원 좌표·집수 경계·연결을 표시용 목록으로 보존."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.published_network import load_archive, records, digest


def derive(raw, catalog):
    if digest(raw) != catalog['sourceOriginalSha256']:
        raise ValueError('관망 원본 해시 불일치')
    _, sections = records(raw)
    units = [r['tokens'][1].lower() for r in sections.get('MAP', [])
             if r['tokens'][0].lower() == 'units' and len(r['tokens']) == 2]
    if units != ['meters']:
        raise ValueError('원본 표시 좌표 단위 미확인')
    polygons, vertices = {}, {}
    for section, grouped in [('POLYGONS', polygons), ('VERTICES', vertices)]:
        for row in sections.get(section, []):
            name, *values = row['tokens']
            point = [float(v) for v in values]
            if len(point) != 2 or not all(math.isfinite(v) for v in point):
                raise ValueError('원 좌표 형식 오류')
            grouped.setdefault(name, []).append(point)
    coords = {r['tokens'][0]: [float(v) for v in r['tokens'][1:]]
              for r in sections['COORDINATES']}
    if len(coords) != len(sections['COORDINATES']):
        raise ValueError('절점 좌표 중복')
    if set(coords) != {r['tokens'][0] for r in sections['JUNCTIONS'] + sections['OUTFALLS']}:
        raise ValueError('절점과 표시 좌표 불일치')
    if not set(vertices) <= {r['tokens'][0] for r in sections['CONDUITS']}:
        raise ValueError('관로 중간 좌표 연결 누락')
    outfalls = {r['tokens'][0] for r in sections['OUTFALLS']}
    nodes = []
    for row in sections['JUNCTIONS'] + sections['OUTFALLS']:
        name = row['tokens'][0]
        point = coords[name]
        if len(point) != 2 or not all(math.isfinite(v) for v in point):
            raise ValueError('절점 좌표 형식 오류')
        nodes.append({'id': name, 'kind': 'OUTFALL' if name in outfalls else 'JUNCTION',
                      'coordinate': point})
    links = []
    for row in sections['CONDUITS']:
        name, start, end = row['tokens'][:3]
        links.append({'id': name, 'fromNode': start, 'toNode': end,
                      'points': [coords[start], *vertices.get(name, []), coords[end]],
                      'lengthDeclaredM': float(row['tokens'][3])})
    if set(polygons) != {c['id'] for c in catalog['catchments']}:
        raise ValueError('집수 경계와 계산 목록 불일치')
    catchments = []
    for c in catalog['catchments']:
        points = polygons[c['id']]
        if len(points) < 3 or len(set(tuple(p) for p in points)) < 3:
            raise ValueError('집수 경계 누락')
        catchments.append({'id': c['id'], 'outletNodeId': c['outletNodeId'],
                           'points': points})
    return {'schemaVersion': 1, 'id': 'SEOCHO_PUBLISHED_NATIVE_LAYOUT_V1',
            'sourceOriginalSha256': digest(raw), 'sourceUrl': catalog['sourceUrl'],
            'classification': 'PUBLISHED_MODEL_COORDINATES_NOT_GEOREFERENCED',
            'coordinateUnitsDeclared': 'Meters', 'horizontalCrs': None,
            'nodes': nodes, 'links': links, 'catchments': catchments,
            'limitations': ['원본 INP의 좌표와 집수 경계를 그대로 표시; 서울 지도 좌표 변환 미적용',
                '집수구역은 계산 경계이며 실제 시설 부지·시공 가능 면적이 아님',
                '화살표는 관로의 정의 방향이며 계산 유량·역류 방향이 아님',
                '구역별 설계 개수는 면적 배분이며 개별 시설의 실제 위치를 뜻하지 않음']}


def main():
    catalog=json.loads((ROOT/'backend/src/main/resources/watersheds/seocho-published-v1.json').read_text())
    _, source_hash, entries=load_archive(ROOT,ROOT/'data/manifests/mendeley-seocho-network-v3.json')
    if source_hash != catalog['sourceManifestSha256']:
        raise ValueError('원본 목록 해시 불일치')
    original=next(v['raw'] for v in entries if v['member']==catalog['sourceMember'])
    value=derive(original,catalog)
    raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
    target=ROOT/'backend/src/main/resources/watersheds/seocho-layout-v1.json'
    if target.exists() and target.read_bytes()!=raw:
        raise ValueError('기존 표시 목록 변경 금지')
    target.write_bytes(raw)
    print(json.dumps({'sha256':digest(raw),'bytes':len(raw),'catchments':len(value['catchments']),
                      'nodes':len(value['nodes']),'links':len(value['links'])}))


if __name__=='__main__': main()
