"""전체 표시 파일과 121종 원본·렌더러 결속 및 대표 도형의 분할 보존 검사."""
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
from shapely.geometry import LineString,MultiPolygon,Point,mapping

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_native_features import EXISTING
from prepare_topography_scene import ORIGIN

BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=source.ROOT/'frontend/public/data'


def verify(samples_path):
    started=time.monotonic()
    index=json.loads((PUBLIC/'seoul-features-v1/index.json').read_bytes())
    semantics=json.loads((source.ROOT/'data/manifests/seoul-topography-semantics-v1.json').read_bytes())['layers']
    assert len(index['layers'])==121 and {row['id'] for row in index['layers']}==set(semantics)
    assert index['generatorSha256']==spatial.file_sha256(source.ROOT/'scripts/prepare_native_features.py')
    assert index['sourceCitySha256']==spatial.file_sha256(PUBLIC/'seoul-native-v1/city.json')
    assert index['sourceStreetLifeSha256']==spatial.file_sha256(PUBLIC/'seoul-street-life-v1/index.json')
    database=BASE/'spatial-v1/spatial.sqlite'
    assert index['sourceSpatialSha256']==spatial.file_sha256(database)
    layer_counts=Counter();representatives={};collected={};totals=Counter();tile_bytes=0
    samples=dict(schemaVersion=1,id='0_0',points=[],lines=[],areas=[])
    with closing(sqlite3.connect('file:'+str(database)+'?mode=ro&immutable=1',uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        sources=dict(db.execute('SELECT layer,COUNT(*) FROM features GROUP BY layer'))
        first_tiles=dict(db.execute('SELECT layer,MIN(tile) FROM layers GROUP BY layer'))
        for number,layer in enumerate(index['layers']):
            assert sources[layer['id']]==layer['sourceCount']
            expected=EXISTING.get(layer['id'],'NATIVE_FEATURE')
            assert layer['renderer']==expected
            if expected=='NATIVE_FEATURE':assert layer['displayPartCount']>0 and layer['uniqueDisplayCount']>0
            row=db.execute('''SELECT fid,geometry_wkb FROM features WHERE tile=? AND layer=?
                AND geometry_status='VALID' AND deleted=0 ORDER BY record_number LIMIT 1''',(first_tiles[layer['id']],layer['id'])).fetchone()
            assert row is not None
            fid,raw=row;geometry=translate(shapely.from_wkb(raw),-ORIGIN[0],-ORIGIN[1])
            representatives[fid]=(number,geometry);collected[fid]=[]
            body=mapping(geometry);kind=body['type'];coordinates=body['coordinates']
            if kind=='Point':key='points';values=[coordinates]
            elif kind in ('LineString','MultiLineString'):key='lines';values=[coordinates] if kind=='LineString' else coordinates
            else:key='areas';values=[coordinates] if kind=='Polygon' else coordinates
            samples[key].append([number,fid,values,None])
        for tile_number,entry in enumerate(index['tiles']):
            raw=(PUBLIC/'seoul-features-v1'/entry['file']).read_bytes()
            assert len(raw)==entry['storedBytes'] and source.digest(raw)==entry['storedSha256']
            tile_bytes+=len(raw);raw=gzip.decompress(raw)
            assert len(raw)==entry['bytes'] and source.digest(raw)==entry['sha256']
            tile=json.loads(raw);assert tile['id']==entry['id']
            fids={row[1] for key in ('points','lines','areas') for row in tile[key]}
            bindings={}
            values=sorted(fids)
            for at in range(0,len(values),500):
                batch=values[at:at+500]
                bindings.update(db.execute('SELECT fid,layer FROM features WHERE fid IN ('+','.join('?' for _ in batch)+')',batch))
            minx,miny,maxx,maxy=entry['bounds']
            for key in ('points','lines','areas'):
                assert len(tile[key])==entry['counts'][key];totals[key]+=len(tile[key])
                for layer,fid,parts,label in tile[key]:
                    assert bindings[fid]==index['layers'][layer]['id']
                    assert index['layers'][layer]['renderer']=='NATIVE_FEATURE'
                    assert label is None or isinstance(label,str) and len(label)<=200
                    layer_counts[layer]+=1
                    points=parts if key=='points' else [p for part in parts for p in part] if key=='lines' else [p for polygon in parts for ring in polygon for p in ring]
                    assert all(minx-1e-7<=p[0]<=maxx+1e-7 and miny-1e-7<=p[1]<=maxy+1e-7 for p in points)
                    if fid in representatives:
                        collected[fid].extend([Point(p) for p in parts] if key=='points' else
                            [LineString(part) for part in parts] if key=='lines' else [MultiPolygon([(part[0],part[1:]) for part in parts])])
            if (tile_number+1)%100==0:print(source.canonical(dict(tiles=tile_number+1,total=len(index['tiles']))),flush=True)
        matched=[]
        for fid,(layer,original) in representatives.items():
            if index['layers'][layer]['renderer']!='NATIVE_FEATURE':continue
            assert collected[fid],f'레이어 대표 도형 누락: {index["layers"][layer]["id"]}'
            merged=shapely.union_all(collected[fid])
            assert merged.hausdorff_distance(original)<1e-7
            assert abs(merged.area-original.area)<max(1e-5,original.area*1e-10)
            assert abs(merged.length-original.length)<max(1e-5,original.length*1e-10)
            matched.append(index['layers'][layer]['id'])
    for number,layer in enumerate(index['layers']):
        if layer['renderer']=='NATIVE_FEATURE':assert layer_counts[number]==layer['displayPartCount']
    samples_path.write_text(source.canonical(samples)+'\n')
    return dict(schemaVersion=1,status='PASS',layerCount=121,newFeatureLayerCount=len(matched),
        existingRendererLayerCount=len(EXISTING),allLayersBound=True,allTileHashesChecked=True,
        allRenderedSourceFidsAndLayersChecked=True,allCoordinatesWithinDisplayTile=True,
        representativeSourceGeometryUnionCheckedLayers=matched,
        sourceCitySha256=index['sourceCitySha256'],sourceSpatialSha256=index['sourceSpatialSha256'],
        indexSha256=spatial.file_sha256(PUBLIC/'seoul-features-v1/index.json'),
        tileCount=len(index['tiles']),storedTileBytes=tile_bytes,displayRecords=dict(totals),
        samplesSha256=spatial.file_sha256(samples_path),hydraulicInputsChanged=False,
        elapsedSeconds=round(time.monotonic()-started,3))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);parser.add_argument('--samples',type=Path,required=True)
    args=parser.parse_args();assert not args.report.exists() and not args.samples.exists()
    report=verify(args.samples);args.report.write_text(source.canonical(report)+'\n');print(source.canonical(report))
