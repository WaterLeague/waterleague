"""보관된 서울 지도 경계에서 구 선택용 평면 도형 추출."""
import hashlib
import json
from pathlib import Path
from shapely.geometry import MultiPolygon

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/public/data/seoul-native-v1/city.json'
EXPECTED = '67a8b80b7036590973b7db99053521333f9405e1076a7939bfe491c43296dd6c'
TARGET = ROOT / 'frontend/src/domains/district/repository/districtMap.json'


def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('서울 지도 원본 해시 불일치')
    city = json.loads(raw)
    points = [p for d in city['districts'] for poly in d['polygons'] for ring in poly for p in ring]
    left, right = min(p[0] for p in points), max(p[0] for p in points)
    bottom, top = min(p[1] for p in points), max(p[1] for p in points)
    scale = 560 / (right-left)

    def point(p):
        return [round(20+(p[0]-left)*scale, 2), round(20+(top-p[1])*scale, 2)]

    districts = []
    for district in city['districts']:
        paths = []
        geometry = MultiPolygon([(poly[0], poly[1:]) for poly in district['polygons']]).simplify(20, preserve_topology=True)
        for polygon in (geometry.geoms if geometry.geom_type == 'MultiPolygon' else [geometry]):
            for ring in [polygon.exterior.coords, *(r.coords for r in polygon.interiors)]:
                xy = [point(p) for p in ring]
                paths.append('M'+'L'.join(f'{x},{y}' for x,y in xy)+'Z')
        districts.append({'id': district['id'], 'name': district['name'],
                          'center': point(district['center']), 'path': ''.join(paths)})
    result = {'sourceSha256': EXPECTED, 'source': '/data/seoul-native-v1/city.json',
              'sourceUrl': 'https://data.seoul.go.kr/dataList/OA-22161/A/1/datasetView.do',
              'use': 'DISTRICT_SELECTION_DISPLAY_ONLY',
              'displaySimplificationM': 20,
              'viewBox': f'0 0 600 {round(40+(top-bottom)*scale, 2)}', 'districts': districts}
    TARGET.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n')
    print(f'서울 {len(districts)}개 구 선택 도형 생성 · {TARGET.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
