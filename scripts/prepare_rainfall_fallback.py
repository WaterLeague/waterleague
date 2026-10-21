"""공개 관측소 좌표로 AWS별 서울시 보조 지점을 사전 고정."""
import hashlib
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from pyproj import Geod
from local_config import ROOT, load
from fetch_seoul_regional_rainfall import stations_at

sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim.spatial.game_catalog import regions


def main():
    load()
    instant = '202610220000'
    primary = stations_at(instant, os.environ['KMA_API_KEY'])
    source = ROOT / 'data/raw/seoul-rain-stations-20260915.xlsx'
    meta = json.loads((ROOT / 'data/manifests/seoul-rain-stations-20260915.xlsx.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == meta['sha256']
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    candidates = []
    with ZipFile(source) as archive:
        strings = [''.join(n.itertext()) for n in ElementTree.fromstring(
            archive.read('xl/sharedStrings.xml')).findall('m:si', ns)]
        for row in ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml')).findall('m:sheetData/m:row', ns)[1:]:
            values = {}
            for cell in row.findall('m:c', ns):
                value = cell.find('m:v', ns)
                if value is not None:
                    column = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                    values[column] = strings[int(value.text)] if cell.attrib.get('t') == 's' else value.text
            candidates.append({'districtName': values['A'], 'name': values['B'],
                'stationId': values['D'], 'longitude': float(values['F']), 'latitude': float(values['G'])})
    geod = Geod(ellps='WGS84')
    bindings = {}
    for station in sorted({v['defaultRainfall']['stationId'] for v in regions().values()}):
        aws = primary[station]
        aws = aws | {'limitation': '2026-10-22 조회 좌표; 전체 이전 이력·부지 강우 대표성 미검증'}
        ranked = sorted((geod.inv(aws['longitude'], aws['latitude'], c['longitude'], c['latitude'])[2],
                         c['stationId'], c) for c in candidates)
        distance, _, selected = ranked[0]
        if distance > 10000:
            raise ValueError('보조 관측소 거리 초과')
        bindings[station] = {'primary': aws, 'secondary': selected, 'distanceM': round(distance, 3)}
    result = {'version': 'SEOUL_NEAREST_GAUGE_ANTECEDENT_V1',
        'selection': 'NEAREST_WGS84_DISTANCE_BEFORE_RAINFALL_LOOKUP_WITHIN_10KM',
        'effectiveFromKst': '2026-10-01T00:00:00+09:00',
        'locationSource': meta, 'primaryLocationTimeKst': instant, 'bindings': bindings}
    path = ROOT / 'backend/src/main/resources/native-weather/v1/antecedent-fallback.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: {'station': v['secondary']['stationId'], 'name': v['secondary']['name'], 'distanceM': v['distanceM']} for k,v in bindings.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
