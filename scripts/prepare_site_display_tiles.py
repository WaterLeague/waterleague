"""검증된 설치 후보의 표시 도형을 공간 타일로 분리한다."""
import gzip, hashlib, json, math
from pathlib import Path
from collections import defaultdict
from shapely.geometry import box
from shapely import union_all
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'backend/src/main/resources/shared-sites'
OUTPUT = ROOT/'frontend/public/data/site-display-v1'
TYPES = ['RAIN_GARDEN','PERMEABLE_PAVEMENT','GREEN_ROOF','BIORETENTION','VEGETATIVE_SWALE','INFILTRATION_TRENCH']
def sha(raw): return hashlib.sha256(raw).hexdigest()
def write(path, value):
    raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return {'bytes':len(raw),'sha256':sha(raw)}
def main():
    occupancy=ROOT/'backend/src/main/resources/infrastructure/seoul-infrastructure-occupancy-20261019-v5.json'
    exclusions={r['districtId']+':'+r['cellId'] for r in json.loads(occupancy.read_bytes())['exclusions']}
    tiles=defaultdict(list); overview_cells={};sources=[];count=0
    for version in (9,10):
        catalog=(SOURCE/f'catalog-v{version}.json').read_bytes();sources.append(sha(catalog))
        for entry in json.loads(catalog)['entries']:
            packed=(SOURCE/entry['file']).read_bytes();raw=gzip.decompress(packed)
            if sha(packed)!=entry['gzipSha256'] or sha(raw)!=entry['sha256']:raise ValueError('후보 원문 해시 오류')
            for cell in json.loads(raw)['cells']:
                if cell['kind']!='GROUND' or entry['districtId']+':'+cell['id'] in exclusions:continue
                coords=cell['coordinates'];xs=[p[0] for p in coords];ys=[p[1] for p in coords]
                row=[cell['id'],entry['districtId'],sum(1<<TYPES.index(t) for t in cell['allowedTypes']),[round(v,3) for p in coords for v in p]]
                for x in range(math.floor(min(xs)/1000),math.floor(max(xs)/1000)+1):
                    for y in range(math.floor(min(ys)/1000),math.floor(max(ys)/1000)+1):tiles[f'{x}_{y}'].append(row)
                for x in range(math.floor(min(xs)/20),math.ceil(max(xs)/20)):
                    for y in range(math.floor(min(ys)/20),math.ceil(max(ys)/20)):
                        key=(entry['districtId'],x,y);overview_cells[key]=overview_cells.get(key,0)|row[2]
                count+=1
    entries=[]
    for key,rows in sorted(tiles.items()):
        x,y=map(int,key.split('_'));file=f'tiles/{key}.json'
        entries.append({'id':key,'file':file,'bounds':[x*1000,y*1000,(x+1)*1000,(y+1)*1000],**write(OUTPUT/file,rows)})
    overview=[];overview_groups=defaultdict(list)
    for (district,x,y),mask in overview_cells.items():overview_groups[(district,mask)].append(box(x*20,y*20,(x+1)*20,(y+1)*20))
    for (district,mask),polygons in sorted(overview_groups.items()):
        merged=union_all(polygons).simplify(.5,preserve_topology=True)
        parts=list(merged.geoms) if hasattr(merged,'geoms') else [merged]
        for poly in parts:
            if poly.geom_type!='Polygon' or poly.is_empty:continue
            flat=lambda ring:[round(v,3) for p in ring.coords for v in p]
            overview.append([f'overview-{len(overview)}',district,mask,flat(poly.exterior),[flat(r) for r in poly.interiors]])
    overview_ref={'file':'overview.json',**write(OUTPUT/'overview.json',overview)}
    ref=write(OUTPUT/'catalog.json' ,{'schemaVersion':1,'sourceCatalogs':sources,'occupancySha256':sha(occupancy.read_bytes()),'types':TYPES,'count':count,'overview':{**overview_ref,'cellSizeM':20,'picking':False},'tiles':entries,'modelInput':False})
    write(ROOT/'data/manifests/site-display-v1.json',{'catalog':ref,'generatorSha256':sha(Path(__file__).read_bytes()),'sourceCatalogs':sources,'occupancySha256':sha(occupancy.read_bytes()),'count':count,'roundingM':.001,'modelInput':False})
    print(json.dumps({'count':count,'tiles':len(entries),'bytes':sum(e['bytes'] for e in entries),'catalog':ref}))
if __name__=='__main__':main()
