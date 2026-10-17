"""공개 형상·포장 태그·토성·DEM을 설치 후보별 수문 입력으로 연결."""
import copy,gzip,hashlib,json,math,subprocess
from collections import Counter
from pathlib import Path
import pyproj
from shapely.geometry import Polygon,shape,Point
from shapely.ops import transform
from shapely.strtree import STRtree
from prepare_seoul_city import ORIGIN
from prepare_shared_site_constraints import ROOT,DIRECTORY,save

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
EPA_URL='https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT'
# USDA 토성군의 단일 실측값으로 오인하지 않도록 가능한 문헌 범위를 보존한다.
SOILS={
 '사질':(29.972,120.396,60.96,'Loamy sand–Sand'),
 '사양질':(3.302,10.922,88.9,'Loam–Sandy loam'),
 '미사사양질':(6.604,6.604,169.926,'Silt loam'),
 '식양질':(1.016,6.604,210.058,'Clay loam–Sandy clay loam–Loam–Silt loam'),
 '미사식양질':(1.016,6.604,270.002,'Silty clay loam–Silt loam'),
 '식질':(.254,1.016,320.04,'Clay–Sandy clay–Silty clay–Clay loam'),
}
ROUGHNESS={'asphalt':.011,'concrete':.012}


def geometry_inputs(cell):
    poly=Polygon(cell['coordinates'])
    if not poly.is_valid or poly.area<=0 or abs(poly.area-cell['areaM2'])>max(.001,poly.area*1e-6):raise ValueError('물리 입력 도형 오류')
    points=list(poly.minimum_rotated_rectangle.exterior.coords)
    length=max(math.dist(a,b) for a,b in zip(points,points[1:]))
    return {'flowLengthM':round(length,6),'runoffWidthM':round(poly.area/length,6),
            'widthMethod':'FOOTPRINT_AREA_OVER_LONG_AXIS','geometrySourceIds':cell['sourceIds']}


def horn(values,dx,dy):
    if len(values)!=9 or any(not math.isfinite(x) or x==-9999 for x in values):return None
    a,b,c,d,e,f,g,h,i=values
    sx=((c+2*f+i)-(a+2*d+g))/(8*dx)
    sy=((g+2*h+i)-(a+2*b+c))/(8*dy)
    return math.hypot(sx,sy)*100


class Terrain:
    def __init__(self):
        path=ROOT/'data/private/seongsu-official-20261017/dem-2025/37705/37705.img'
        self.hash=sha(path.read_bytes())
        if self.hash!='70f03190643ea70276d70a2e869397c199dfb9370caf835c8806a75f75abd522':raise ValueError('등록된 DEM 원문 해시 불일치')
        info=json.loads(subprocess.check_output(['gdalinfo','-json',str(path)]))
        self.w,self.h=info['size'];self.gt=info['geoTransform']
        if self.gt[1:] != [90.0,0.0,1972260.0,0.0,-90.0]:raise ValueError('DEM 격자 변경')
        self.xy=pyproj.Transformer.from_crs(5186,pyproj.CRS.from_wkt(info['coordinateSystem']['wkt']),always_xy=True,allow_ballpark=False)
        rows=subprocess.check_output(['gdal_translate','-q','-of','XYZ',str(path),'/vsistdout/'],text=True).splitlines()
        self.values=[float(row.split()[2]) for row in rows]
        if len(self.values)!=self.w*self.h:raise ValueError('DEM 셀 수 오류')
    def sample(self,cell):
        if cell['kind']!='GROUND':return None
        x,y=self.xy.transform(cell['center'][0]+ORIGIN[0],cell['center'][1]+ORIGIN[1],errcheck=True)
        col=math.floor((x-self.gt[0])/self.gt[1]);row=math.floor((y-self.gt[3])/self.gt[5])
        if not(1<=col<self.w-1 and 1<=row<self.h-1):return None
        z=[self.values[(row+j)*self.w+col+i] for j in (-1,0,1) for i in (-1,0,1)]
        slope=horn(z,90,90)
        if slope is None:return None
        return {'slopePercent':round(slope,6),'slopeMethod':'NGII_2025_90M_HORN_TERRAIN_PROXY',
                'terrainCell':[col,row],'terrainResolutionM':90,'terrainSourceSha256':self.hash}


def main():
    prior_raw=(DIRECTORY/'catalog-v3.json').read_bytes()
    if sha(prior_raw)!='80e46a9c3821cdeff4b9acd839b264d810ba559202da828cdb8a6b45c04b15e4':raise ValueError('이전 후보 목록 오류')
    osm_manifest=json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_bytes())
    raw=(ROOT/'data/private/seoul-city-20261017/seoul-polygons.geojson').read_bytes()
    if sha(raw)!=osm_manifest['extractHashes']['seoul-polygons.geojson']:raise ValueError('OSM 원문 오류')
    tags={}
    for f in json.loads(raw)['features']:
        p=f['properties'];identifier='relation/'+p['osm_id'] if p.get('osm_id') else 'way/'+p['osm_way_id']
        t=p.get('other_tags') or {};tags[identifier]=json.loads(t) if isinstance(t,str) else t
    source_raw=(ROOT/'data/manifests/seoul-soil-20261018.json').read_bytes();source=json.loads(source_raw)
    geometries=[];features=[];invalid=0
    projection=pyproj.Transformer.from_crs(4326,5186,always_xy=True,allow_ballpark=False)
    for page in source['pages']:
        raw=(ROOT/page['file']).read_bytes()
        if sha(raw)!=page['sha256']:raise ValueError('토성 원문 해시 오류')
        for feature in json.loads(raw)['response']['result']['featureCollection']['features']:
            g=transform(projection.transform,shape(feature['geometry']))
            if not g.is_valid or g.is_empty:invalid+=1;continue
            geometries.append(g);features.append(feature)
    tree=STRtree(geometries);terrain=Terrain();stats=Counter();entries=[]
    for e in json.loads(prior_raw)['entries']:
        raw=(DIRECTORY/e['file']).read_bytes()
        if sha(raw)!=e['gzipSha256']:raise ValueError('후보 압축 오류')
        raw=gzip.decompress(raw)
        if sha(raw)!=e['sha256']:raise ValueError('후보 원문 오류')
        snapshot=json.loads(raw)
        for c in snapshot['cells']:
            v=geometry_inputs(c);stats['geometry']+=1
            t=tags.get(c['sourceIds'][0],{});surface=t.get('surface') if c['kind']=='GROUND' else t.get('roof:material')
            v['surfaceTag']=surface
            v['imperviousBasis']='BUILDING_ROOF_CLASSIFICATION' if c['kind']=='ROOF' else 'SURFACE_UNKNOWN_ASSUMPTION'
            if c['kind']=='GROUND' and surface in ROUGHNESS:
                v.update({'nImpervious':ROUGHNESS[surface],'imperviousBasis':'OSM_SEALED_MATERIAL_CLASSIFICATION'});stats['material']+=1
            terrain_value=terrain.sample(c)
            if terrain_value:v.update(terrain_value);stats['terrainSlope']+=1
            else:v.update({'slopePercent':1,'slopeMethod':'UNRESOLVED_DESIGN_ASSUMPTION'})
            v['soilStatus']='NOT_APPLICABLE_ROOF' if c['kind']=='ROOF' else 'UNRESOLVED'
            if c['kind']=='GROUND':
                poly=Polygon([(x+ORIGIN[0],y+ORIGIN[1]) for x,y in c['coordinates']])
                hit=[int(i) for i in tree.query(poly,predicate='intersects') if geometries[int(i)].intersection(poly).area>1e-6]
                if len(hit)==1 and geometries[hit[0]].covers(poly):
                    f=features[hit[0]];label=f['properties']['label'];v.update({'soilClass':label,'soilFeatureId':f['id']})
                    if label in SOILS:
                        low,high,suction,texture=SOILS[label]
                        v.update({'soilStatus':'TEXTURE_CLASS_LITERATURE_ESTIMATE','conductivityMmH':low,
                          'conductivityRangeMmH':[low,high],'suctionMm':suction,'textureReference':texture});stats['soil']+=1
                else:stats['soilBoundaryOrGap']+=1
            c['physicalInputs']=v
        snapshot.update({'schemaVersion':4,'previousSnapshotSha256':e['sha256'],'constraintVersion':'PUBLIC_SITE_PHYSICS_V4',
          'physicsEvidence':{'soilManifestSha256':sha(source_raw),'terrainSourceSha256':terrain.hash,'osmExtractSha256':osm_manifest['extractHashes']['seoul-polygons.geojson'],
             'referenceUrl':EPA_URL,'taxonomyUrl':'https://www.nrcs.usda.gov/sites/default/files/2022-09/Keys-to-Soil-Taxonomy.pdf','roughnessReference':'Appendix A.6','soilReference':'Appendix A.2; Korean particle-size family crosswalk; lower K scenario',
             'widthMethod':'공개 도형 면적 / 최소 회전 외접사각형 장축; 실제 배수 방향 미확인',
             'slopeMethod':'지상 후보만 2025 공개 DEM의 90m 격자·3×3 Horn 지역 경사 대용값; 포장면 실측 경사 아님',
             'soilMethod':'원본 전체 포함·단일 토성만 매칭; 토성군을 EPA 문헌 범위로 환산한 저투수 시나리오, 현장 침투시험 아님'},
          'limitations':['옥상 경사·배수구 및 미분류 표면은 실측 미확보','DEM 경사는 270m 창의 지역 지형 추정이며 도로 턱·건물별 지붕 경사 아님','심토토성은 도시 성토·다짐·공학적 식재토를 확정하지 않음','시설 두께·재료·초기 수분은 설계 시나리오']})
        raw=encode(snapshot);zipped=gzip.compress(raw,mtime=0);name=e['districtId']+'-v4.json.gz';save(DIRECTORY/name,zipped)
        entries.append(e|{'file':name,'sha256':sha(raw),'gzipSha256':sha(zipped),'bytes':len(raw)})
        print(e['districtName'],len(snapshot['cells']),flush=True)
    value={'schemaVersion':4,'previousCatalogSha256':sha(prior_raw),'generatorSha256':sha(Path(__file__).read_bytes()),
           'sourceManifestSha256':sha(source_raw),'coverage':dict(stats),'invalidSoilFeatures':invalid,'entries':entries}
    raw=encode(value);save(DIRECTORY/'catalog-v4.json',raw);save(ROOT/'data/manifests/shared-sites-v4.json',raw)
    print('catalog',sha(raw),'coverage',dict(stats),flush=True)
if __name__=='__main__':main()
