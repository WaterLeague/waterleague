"""서울시 공개 실시간 도시자료의 121장소 경계 변환."""
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

import shapely
from shapely.affinity import translate
from shapely.geometry import shape, mapping
from fetch_seoul_observations import SOURCES, fetch
from prepare_seoul_city import ROOT, ORIGIN, digest, write


def main():
    name = 'seoul-citydata-121-areas-20260414.zip'
    SOURCES['city-areas'] = ('OA-21778', '16', '2', name, 2_000_000)
    fetch('city-areas')
    path = ROOT / 'data/raw' / name
    with zipfile.ZipFile(path) as archive:
        entries = [n for n in archive.namelist() if n.endswith('.shp')]
        if len(entries) != 1: raise ValueError('경계 파일 구성 오류')
        source = '/vsizip/' + str(path) + '/' + entries[0]
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / 'areas.json'
        subprocess.run(['ogr2ogr', '-f', 'GeoJSON', str(target), source, '-t_srs', 'EPSG:5186'], check=True)
        features = json.loads(target.read_text())['features']
    areas = []
    repairs = []
    for feature in features:
        g = translate(shape(feature['geometry']), -ORIGIN[0], -ORIGIN[1])
        if not g.is_valid:
            fixed = shapely.make_valid(g, method='structure')
            if abs(fixed.area - g.area) > 0.1: raise ValueError('경계 보정 면적 초과')
            repairs.append({'id':feature['properties']['AREA_CD'],'reason':shapely.is_valid_reason(g),
                            'method':'shapely.make_valid structure','areaChangeM2':fixed.area-g.area})
            g = fixed
        if not g.is_valid or g.is_empty or g.geom_type not in ('Polygon', 'MultiPolygon'): raise ValueError('장소 경계 오류')
        if g.geom_type == 'Polygon': g = shapely.MultiPolygon([g])
        p = feature['properties']
        areas.append({'id':p['AREA_CD'], 'name':p['AREA_NM'], 'areaKm2':round(g.area / 1_000_000,8),
                      'bounds':list(g.bounds), 'polygons':mapping(g)['coordinates']})
    if len(areas) != 121 or len({a['id'] for a in areas}) != 121: raise ValueError('장소 수 불일치')
    data = {'schemaVersion':1, 'originProjected':ORIGIN, 'coordinateSystem':'EPSG:5186',
            'sourceDate':'2026-04-14', 'sourceSha256':digest(path),
            'sourceUrl':'https://data.seoul.go.kr/dataList/OA-21778/A/1/datasetView.do',
            'license':'공공누리 제1유형 / 서울특별시', 'topologyRepairs':repairs, 'areas':sorted(areas,key=lambda a:a['id'])}
    output = write(ROOT / 'frontend/public/data/city-live-areas-v1.json',data)
    write(ROOT / 'backend/src/main/resources/urban/city-live-areas-v1.json',data)
    write(ROOT / 'data/manifests/city-live-areas-v1.json',{'sourceSha256':digest(path),'generatorSha256':digest(Path(__file__)), 'output':output})
    print(output)


if __name__ == '__main__': main()
