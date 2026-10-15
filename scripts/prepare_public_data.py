"""확보한 공개 원본에서 시각화 자료와 품질 요약 생성."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
ORIGIN = (127.054, 37.54425)
BOUNDS = (127.0525, 37.5430, 127.0555, 37.5455)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(lon, lat):
    # 화면 전용 근거리 투영이며 수문 면적 산정에는 별도 검증된 CRS를 사용한다.
    return [round((lon - ORIGIN[0]) * 111320 * math.cos(math.radians(ORIGIN[1])), 3),
            round((lat - ORIGIN[1]) * 111320, 3)]


def positive_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and 0 < result < 500 else None
    except (ValueError, TypeError):
        return None


def prepare_map():
    path = RAW / 'seongsu.osm'
    root = ET.parse(path).getroot()
    nodes = {n.attrib['id']: (float(n.attrib['lon']), float(n.attrib['lat'])) for n in root.findall('node')}
    features = []
    for way in root.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        refs = [n.attrib['ref'] for n in way.findall('nd')]
        if any(ref not in nodes for ref in refs):
            continue
        coords = [nodes[ref] for ref in refs]
        if len(coords) < 2:
            continue
        if 'building' in tags and tags['building'] != 'no' and len(coords) >= 4 and refs[0] == refs[-1]:
            center = [sum(p[i] for p in coords[:-1]) / (len(coords) - 1) for i in (0, 1)]
            if not (BOUNDS[0] <= center[0] <= BOUNDS[2] and BOUNDS[1] <= center[1] <= BOUNDS[3]):
                continue
            height = positive_number(tags.get('height'))
            levels = positive_number(tags.get('building:levels'))
            source = 'OSM_TAG' if height else 'LEVELS_ESTIMATE' if levels else 'VISUAL_ASSUMPTION'
            height = height or (levels * 3.2 if levels else 9.6)
            points = [project(*c) for c in coords]
            area = abs(sum(points[i][0]*points[i+1][1]-points[i+1][0]*points[i][1] for i in range(len(points)-1))) / 2
            features.append({'id': f"way/{way.attrib['id']}", 'kind': 'building', 'name': tags.get('name', ''),
                'coordinates': points, 'geographicCoordinates': coords, 'heightM': round(height, 2), 'heightSource': source,
                'displayAreaM2': round(area, 1), 'center': project(*center), 'osmVersion': way.attrib.get('version'),
                'sourceUpdatedAt': way.attrib.get('timestamp')})
        elif tags.get('highway') in {'residential','tertiary','secondary','primary','service','pedestrian','footway','living_street','unclassified'}:
            # 후보 경계를 벗어난 도로는 화면 범위 안의 선분만 제공한다.
            points = [project(*c) for c in coords]
            features.append({'id': f"way/{way.attrib['id']}", 'kind': 'road', 'name': tags.get('name',''),
                'coordinates': points, 'highway': tags['highway']})
    return {'id': 'seongsu-candidate-01', 'title': '서울 성수동', 'subtitle': '연무장길 일대',
        'origin': ORIGIN, 'bounds': BOUNDS, 'widthM': round((BOUNDS[2]-BOUNDS[0])*111320*math.cos(math.radians(ORIGIN[1])),2),
        'depthM': round((BOUNDS[3]-BOUNDS[1])*111320,2), 'validationLevel': 'DRAFT',
        'officialEvaluationAvailable': False, 'sourceHash': digest(path), 'features': features,
        'attribution': '© OpenStreetMap contributors', 'licenseUrl': 'https://www.openstreetmap.org/copyright',
        'limitations': ['후보 지역의 시각화 자료이며 승인된 수문모델 아님', '표고 미확보로 평탄화한 지면',
            '높이 누락은 층수×3.2m 또는 9.6m의 표현용 가정', '도로 폭은 표현용 가정',
            'way 형상만 포함, relation·중정·복잡한 지붕 미반영', '화면 투영 면적은 공식 설치면적 아님']}


def audit_rainfall():
    path=RAW/'seoul-2024.csv'
    with path.open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    periods=Counter()
    for row in rows:
        for key,value in row.items():
            if key in {'AA1','AA2','AA3','AA4'} and value:
                periods[value.split(',')[0]]+=1
    return {'id':'noaa-seoul-2024', 'provider':'NOAA NCEI', 'stationId':'47108099999', 'stationName':rows[0]['NAME'],
        'sourceUrl':'https://noaa-global-hourly-pds.s3.amazonaws.com/2024/47108099999.csv',
        'sourceHash':digest(path),'acquiredAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),'sizeBytes':path.stat().st_size,'rowCount':len(rows),'periodCounts':dict(sorted(periods.items())),
        'status':'REJECTED_FOR_SIMULATION','reason':'누적기간 혼합·결측·품질코드의 이벤트별 검증 미완료',
        'intervalInterpretation':'AA1~AA4의 첫 필드는 누적 시간, 99는 결측 코드. 자료 상세는 ISD 명세 확인 필요.',
        'usableRainfallEventCount':0}


def main():
    snapshot=prepare_map()
    rainfall=audit_rainfall()
    output=ROOT/'frontend/public/data/seongsu.json'
    output.write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n')
    source=RAW/'seongsu.osm'
    manifest={'schemaVersion':1,'map':{'sourceUrl':'https://api.openstreetmap.org/api/0.6/map?bbox=127.0525,37.5430,127.0555,37.5455',
        'provider':'OpenStreetMap contributors','license':'ODbL-1.0','licenseUrl':'https://opendatacommons.org/licenses/odbl/1-0/',
        'sourceHash':digest(source),'sourceBytes':source.stat().st_size,'derivedHash':digest(output),
        'acquiredAt':datetime.fromtimestamp(source.stat().st_mtime,timezone.utc).isoformat(),
        'buildings':sum(f['kind']=='building' for f in snapshot['features']), 'status':'VISUALIZATION_ONLY',
        'transform':'scripts/prepare_public_data.py','transformSha256':digest(Path(__file__)),'coordinateSystem':'WGS84 with local equirectangular display projection',
        'limitations':snapshot['limitations']},'rainfall':rainfall}
    (ROOT/'data/manifests/public-data-audit.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'frontend/public/data/rainfall-audit.json').write_text(json.dumps(rainfall,ensure_ascii=False,indent=2)+'\n')
    print('Published buildings:',manifest['map']['buildings'],'rainfall status:',rainfall['status'])

if __name__=='__main__':main()
