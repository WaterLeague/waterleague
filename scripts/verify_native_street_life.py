"""표시 도형·경로·차량 위치를 원 공간 자료와 독립 대조한다."""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import time

import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, shape

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_objects import object_key
from prepare_topography_scene import ORIGIN

ROOT=source.ROOT
BASE=ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=ROOT/'frontend/public/data'


def read(path, expected=None):
    raw=path.read_bytes()
    if expected is not None:
        assert source.digest(raw)==expected,'표시 입력 해시 불일치'
    return json.loads(raw)


def verify():
    started=time.monotonic()
    index=read(PUBLIC/'seoul-street-life-v1/index.json')
    city_path=PUBLIC/'seoul-native-v1/city.json'
    city=read(city_path,index['sourceCitySha256'])
    assert index['sourceObjectsSha256']==city['sourceObjectsSha256']
    assert spatial.file_sha256(BASE/'objects-v1/objects.sqlite')==city['sourceObjectsSha256']
    assert spatial.file_sha256(BASE/'spatial-v1/spatial.sqlite')==index['sourceSpatialSha256']
    assert spatial.file_sha256(BASE/'scene-v1/catalog.json')==index['sourceSceneSha256']
    assert spatial.file_sha256(ROOT/'scripts/prepare_native_street_life.py')==index['generatorSha256']
    originals={}
    with closing(sqlite3.connect('file:'+str(BASE/'objects-v1/objects.sqlite')+'?mode=ro&immutable=1',uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        for identifier,raw in db.execute("SELECT object_id,geometry_wkb FROM objects WHERE role='SIDEWALK_AREA'"):
            originals[identifier]=translate(shapely.from_wkb(raw),-ORIGIN[0],-ORIGIN[1])
    raw_shapes={}
    with closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro&immutable=1',uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        for layer,raw in db.execute("""SELECT layer,geometry_wkb FROM features
            WHERE layer IN ('N1A_A0043325','N1A_C0430000') AND geometry_status='VALID' AND deleted=0"""):
            geometry=shapely.from_wkb(raw)
            raw_shapes[object_key(layer,geometry)]=translate(geometry,-ORIGIN[0],-ORIGIN[1])
    originals.update(raw_shapes)
    counts=Counter();seen=set();paths=set()
    assert {entry['id'] for entry in index['tiles']}=={entry['id'] for entry in city['tiles']}
    for entry in index['tiles']:
        stored=(PUBLIC/'seoul-street-life-v1'/entry['file']).read_bytes()
        assert source.digest(stored)==entry['storedSha256'] and len(stored)==entry['storedBytes']
        raw=gzip.decompress(stored)
        assert source.digest(raw)==entry['sha256'] and len(raw)==entry['bytes']
        tile=json.loads(raw);assert tile['id']==entry['id']
        for crossing in tile['crosswalks']:
            identifier=crossing['id'];assert identifier not in seen;seen.add(identifier)
            geometry=shape(dict(type='MultiPolygon',coordinates=crossing['polygons']))
            assert geometry.equals(originals[identifier]),'횡단보도 원형 누락·변형'
            for rings in crossing['stripes']:
                stripe=Polygon(rings[0],rings[1:])
                assert stripe.is_valid and stripe.difference(geometry).area<1e-6,'횡단보도 밖 줄무늬'
            counts['crosswalks']+=1
        for lot in tile['parkingLots']:
            identifier=lot['id'];assert identifier not in seen;seen.add(identifier)
            geometry=shape(dict(type='MultiPolygon',coordinates=lot['polygons']))
            assert geometry.equals(originals[identifier]),'주차장 원형 누락·변형'
            assert lot['displayOnly'] and not lot['supports']
            for slot in lot['slots']:
                car=Polygon(slot['corners'])
                assert car.is_valid and car.difference(geometry).area<1e-6,'주차장 밖 정차 차량'
                assert 0<=slot['seed']<1
            counts['parkingLots']+=1;counts['parkedCarPositions']+=len(lot['slots'])
        for path in tile['walkPaths']:
            assert path['id'] not in paths;paths.add(path['id'])
            geometry=originals[path['sourceObjectId']]
            line=LineString(path['coordinates'])
            assert line.is_valid and line.length>=5
            assert geometry.buffer(-0.399999).covers(line),'보도·횡단보도 밖 보행 경로'
            counts['walkPaths']+=1
    assert dict(counts)==index['counts']
    overview=read(PUBLIC/'seoul-overview-v1/index.json')
    assert overview['sourceCitySha256']==spatial.file_sha256(city_path)
    assert spatial.file_sha256(ROOT/'scripts/package_native_overview.py')==overview['generatorSha256']
    levels=[]
    for entry in overview['levels']:
        stored=(PUBLIC/'seoul-overview-v1'/entry['file']).read_bytes()
        assert source.digest(stored)==entry['storedSha256']
        raw=gzip.decompress(stored);assert len(raw)==entry['bytes'] and source.digest(raw)==entry['sha256']
        records=json.loads(raw)['buildings'];assert len(records)==entry['count']
        assert all(0<row[2]<=20000 and 0<row[3]<=20000 and 0<row[4]<=650 and
            0<=row[5]<25 and 0<=row[6]<len(city['tiles']) for row in records)
        assert set(row[5] for row in records)==set(range(25))
        levels.append(dict(spacingM=entry['spacingM'],count=len(records),storedBytes=len(stored)))
    return dict(schemaVersion=1,status='PASS',sourceCitySha256=spatial.file_sha256(city_path),
        sourceSpatialSha256=index['sourceSpatialSha256'],sourceObjectsSha256=index['sourceObjectsSha256'],
        streetIndexSha256=spatial.file_sha256(PUBLIC/'seoul-street-life-v1/index.json'),
        overviewIndexSha256=spatial.file_sha256(PUBLIC/'seoul-overview-v1/index.json'),counts=dict(counts),overview=levels,
        sourceGeometryPreserved=True,walkPathsInsideSourceWithClearance=True,parkingCarsInsideSource=True,
        observedAgentPositions=False,parkingStallsProvided=False,hydraulicInputsChanged=False,
        elapsedSeconds=round(time.monotonic()-started,3),shapelyVersion=shapely.__version__)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args();assert not args.report.exists()
    report=verify();args.report.write_text(source.canonical(report)+'\n');print(source.canonical(report))
