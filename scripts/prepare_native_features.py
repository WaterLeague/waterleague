"""121종 원 레이어를 기존 지도 또는 손실없는 표시 타일에 연결한다."""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import json
import math
from pathlib import Path
import sqlite3
import time

import shapely
from shapely.affinity import translate
from shapely.geometry import box, mapping, Point

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_scene import ORIGIN

BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=source.ROOT/'frontend/public/data'
EXISTING={
    'N1A_B0010000':'NATIVE_BUILDING','N1A_A0070000':'NATIVE_BRIDGE','N1A_E0032111':'NATIVE_WATER','N1A_E0052114':'NATIVE_WATER',
    'N1A_A0043325':'NATIVE_CROSSWALK','N1A_C0430000':'NATIVE_PARKING'}


def parts(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type==kind:
        return [geometry]
    return [part for child in getattr(geometry,'geoms',[]) for part in parts(child,kind)]


def clipped_parts(geometry):
    minx,miny,maxx,maxy=geometry.bounds
    firstx,lastx=math.floor(minx/1000),math.floor(maxx/1000)
    firsty,lasty=math.floor(miny/1000),math.floor(maxy/1000)
    if (lastx-firstx+1)*(lasty-firsty+1)>4096:
        raise ValueError('원 도형 범위 확인 필요')
    kind='Point' if geometry.geom_type=='Point' else 'LineString' if 'Line' in geometry.geom_type else 'Polygon'
    for x in range(firstx,lastx+1):
        for y in range(firsty,lasty+1):
            cell=box(x*1000,y*1000,(x+1)*1000,(y+1)*1000)
            clipped=geometry if firstx==lastx and firsty==lasty else geometry.intersection(cell)
            values=parts(clipped,kind)
            if values:
                yield f'{x}_{y}',kind,values


def style(layer, name):
    code=layer[4:]
    if 'D003' in code:
        return 'TREE','#527c48'
    if any(value in code for value in ('C022','C049')):
        return 'LIGHT','#ae873c'
    if 'C025' in code:
        return 'HYDRANT','#b95540'
    if 'H004' in code or 'H005' in code:
        return 'LABEL','#526b65'
    if any(value in code for value in ('C005','C006','C007','E001','E002','E004','E006','E007')):
        return 'WATER_STRUCTURE','#567e88'
    if any(value in code for value in ('A015','A017','A019','A020')):
        return 'RAIL','#535b62'
    if any(value in code for value in ('F001','F002','F003','F004')):
        return 'TERRAIN','#869276'
    if 'B002' in code:
        return 'WALL','#807c70'
    if any(value in code for value in ('A005','A006','A008','A009','A010','A003','C039','C045','C046','C052','C053')):
        return 'TRANSPORT','#9b9885'
    if code.startswith('G') or code.startswith('H'):
        return 'REFERENCE','#81907d'
    return 'FACILITY','#8e8171'


def build(output):
    if output.exists() or output.is_symlink():
        raise ValueError('기존 전체 지형지물 묶음 덮어쓰기 금지')
    started=time.monotonic()
    path=BASE/'spatial-v1/spatial.sqlite'
    summary=json.loads((BASE/'spatial-v1/summary.json').read_bytes())
    if spatial.file_sha256(path)!=summary['spatialSha256']:
        raise ValueError('원 공간 자료 해시 불일치')
    semantics=json.loads((source.ROOT/'data/manifests/seoul-topography-semantics-v1.json').read_bytes())['layers']
    layers=[]
    for identifier,item in sorted(semantics.items()):
        name=item.get('name') or '자전거·보행 도로(원본 구분)'
        symbol,color=style(identifier,name)
        layers.append(dict(id=identifier,name=name,role=item['role'],shapeType=item['shapeType'],
            scaleDenominator=item['scaleDenominator'],symbol=symbol,color=color,
            renderer=EXISTING.get(identifier,'NATIVE_FEATURE'),sourceCount=0,uniqueDisplayCount=0,displayPartCount=0))
    positions={layer['id']:index for index,layer in enumerate(layers)}
    output.mkdir();(output/'tiles').mkdir()
    database=output/'staging.sqlite'
    missing=[];duplicates=0;counts=Counter()
    try:
        with closing(sqlite3.connect(database)) as staging, closing(sqlite3.connect('file:'+str(path)+'?mode=ro&immutable=1',uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            staging.executescript('''PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-131072;
                CREATE TABLE seen(layer INTEGER,sha BLOB,PRIMARY KEY(layer,sha)) WITHOUT ROWID;
                CREATE TABLE records(tile TEXT,kind TEXT,layer INTEGER,fid INTEGER,body TEXT);''')
            layer_counts=dict(db.execute('SELECT layer,COUNT(*) FROM features GROUP BY layer'))
            for layer in layers:
                layer['sourceCount']=layer_counts.get(layer['id'],0)
            for row_number,(fid,layer,raw,status,properties) in enumerate(db.execute('''SELECT fid,layer,geometry_wkb,geometry_status,properties
                    FROM features WHERE deleted=0 AND layer NOT IN ('''+','.join('?' for _ in EXISTING)+') ORDER BY fid',list(EXISTING))):
                index=positions[layer]
                if raw is None:
                    missing.append(dict(fid=fid,layer=layer,status=status));continue
                geometry=shapely.from_wkb(raw)
                if geometry.is_empty:
                    missing.append(dict(fid=fid,layer=layer,status='EMPTY'));continue
                key=shapely.to_wkb(shapely.normalize(geometry),byte_order=1)
                cursor=staging.execute('INSERT OR IGNORE INTO seen VALUES(?,?)',(index,bytes.fromhex(source.digest(key))))
                if cursor.rowcount==0:
                    duplicates+=1;continue
                if not geometry.is_valid:
                    original=geometry
                    geometry=geometry.boundary
                    if geometry.is_empty and original.geom_type=='LineString':
                        geometry=Point(original.coords[0])
                        counts['invalidSourceAnchor']+=1
                    counts['invalidOutline']+=1
                relative=translate(geometry,-ORIGIN[0],-ORIGIN[1])
                label=None
                if layers[index]['symbol']=='LABEL':
                    label=json.loads(properties).get('명칭')
                    if label is not None and (not isinstance(label,str) or len(label)>200):
                        label=None
                for tile,kind,geometries in clipped_parts(relative):
                    if kind=='Point':
                        values=[list(part.coords)[0] for part in geometries]
                    elif kind=='LineString':
                        values=[list(part.coords) for part in geometries if part.length>0]
                    else:
                        values=[mapping(part)['coordinates'] for part in geometries if part.area>0]
                    if not values:
                        continue
                    payload=[index,fid,values,label]
                    staging.execute('INSERT INTO records VALUES(?,?,?,?,?)',(tile,kind,index,fid,source.canonical(payload)))
                    layers[index]['displayPartCount']+=1;counts[kind]+=len(geometries)
                layers[index]['uniqueDisplayCount']+=1
                if (row_number+1)%100000==0:
                    print(source.canonical(dict(records=row_number+1,seconds=round(time.monotonic()-started,1))),flush=True)
            staging.commit()
            staging.execute('CREATE INDEX tile_rows ON records(tile,kind,layer,fid)')
            staging.commit()
            entries=[]
            tiles=[row[0] for row in staging.execute('SELECT DISTINCT tile FROM records ORDER BY tile')]
            for tile_number,tile in enumerate(tiles):
                body=dict(schemaVersion=1,id=tile,points=[],lines=[],areas=[])
                for kind,encoded in staging.execute('SELECT kind,body FROM records WHERE tile=? ORDER BY kind,layer,fid',(tile,)):
                    body[{'Point':'points','LineString':'lines','Polygon':'areas'}[kind]].append(json.loads(encoded))
                raw=(source.canonical(body)+'\n').encode()
                if len(raw)>32*1024**2:
                    raise ValueError('전체 지형지물 타일 용량 초과')
                stored=gzip.compress(raw,compresslevel=6,mtime=0)
                name='tiles/'+tile+'.json.gz';(output/name).write_bytes(stored)
                x,y=map(int,tile.split('_'))
                entries.append(dict(id=tile,file=name,bounds=[x*1000,y*1000,(x+1)*1000,(y+1)*1000],
                    sha256=source.digest(raw),bytes=len(raw),storedSha256=source.digest(stored),storedBytes=len(stored),
                    counts={key:len(body[key]) for key in ('points','lines','areas')}))
                if (tile_number+1)%100==0:
                    print(source.canonical(dict(tiles=tile_number+1,total=len(tiles))),flush=True)
        database.unlink()
        index=dict(schemaVersion=1,id='SEOUL_NGII_ALL_LAYERS_V1',sourceSpatialSha256=summary['spatialSha256'],
            sourceCitySha256=spatial.file_sha256(PUBLIC/'seoul-native-v1/city.json'),
            sourceStreetLifeSha256=spatial.file_sha256(PUBLIC/'seoul-street-life-v1/index.json'),
            sourceSemanticsSha256=spatial.file_sha256(source.ROOT/'data/manifests/seoul-topography-semantics-v1.json'),
            generatorSha256=spatial.file_sha256(__file__),originProjected=ORIGIN,layers=layers,tiles=entries,
            counts=dict(counts),duplicatesExcluded=duplicates,missingGeometry=missing,
            policy=dict(allLayerRenderersBound=True,tileClippingIsDisplayOnly=True,sourceVertexPrecisionReduced=False,
                sourceFidBoundToSpatialHash=True,hydraulicInputsChanged=False,geometryRepair=False,
                invalidGeometryDisplay='SOURCE_BOUNDARY_WHEN_AVAILABLE',pointSymbolDimensionsAreAssumptions=True),
            versions=dict(shapely=shapely.__version__,geos=shapely.geos_version_string))
        (output/'index.json').write_text(source.canonical(index)+'\n')
        print(source.canonical(dict(indexSha256=spatial.file_sha256(output/'index.json'),counts=dict(counts),
            layerCount=len(layers),tiles=len(entries),seconds=round(time.monotonic()-started,1))),flush=True)
    except BaseException:
        print('전체 지형지물 생성 중단: 미완료 출력 보존',flush=True)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=PUBLIC/'seoul-features-v1')
    build(parser.parse_args().output.absolute())
