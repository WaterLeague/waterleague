"""보관 공개 지도 저류 영역과 현재 지상 후보의 교차 면적 보존."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import pyproj
import shapely
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'seoul-basin-footprints-20261018-v1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    data = (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError('기존 공개자료 버전 덮어쓰기 금지')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha(data)


def overlap(cell, geometry):
    if cell['kind'] != 'GROUND':
        return 0.
    candidate = Polygon(cell['coordinates'])
    if not candidate.is_valid or candidate.is_empty:
        raise ValueError('후보 도형 오류')
    return candidate.intersection(geometry).area if candidate.intersects(geometry) else 0.


def build():
    registry = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_bytes())
    directory = ROOT/registry['sourceDirectory']
    source = directory/'seoul-polygons.geojson'
    if file_sha(source) != registry['extractHashes'][source.name]:
        raise ValueError('보관 서울 원본 해시 불일치')
    if file_sha(directory/'south-korea-261016.osm.pbf') != registry['sourceSha256']:
        raise ValueError('보관 PBF 원본 해시 불일치')
    query = "landuse = 'basin' OR other_tags LIKE '%\"basin\"%'"
    raw = subprocess.run(['ogr2ogr','-f','GeoJSON','/vsistdout/',str(source),
                          '-where',query],check=True,capture_output=True,timeout=60).stdout
    city_raw = (ROOT/'frontend/public/data/seoul-v1/city.json').read_bytes()
    if sha(city_raw) != registry['city']['sha256']:
        raise ValueError('서울 경계 해시 불일치')
    districts = [(d['id'], MultiPolygon([Polygon(p[0],p[1:]) for p in d['polygons']]))
                 for d in json.loads(city_raw)['districts']]
    city = unary_union([g for _,g in districts])
    transformer = pyproj.Transformer.from_crs(4326,5186,always_xy=True,allow_ballpark=False)
    assets, originals, shapes = [], [], {}
    for feature in json.loads(raw)['features']:
        props = feature['properties']
        tags = props.get('other_tags') or {}
        if not isinstance(tags,dict):
            raise ValueError('원본 태그 해석 필요')
        if (tags.get('basin') not in ('detention','retention','infiltration')
            or tags.get('covered') not in (None,'no') or tags.get('location') in ('underground','roof')
            or tags.get('layer') not in (None,'0') or props.get('building') not in (None,'no')):
            continue
        original = shape(feature['geometry'])
        if not original.is_valid or original.is_empty or original.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError('저류 영역 원본 도형 오류')
        geom = translate(shapely.transform(original,transformer.transform,interleaved=False),-198128.,-551989.)
        if geom.intersection(city).area <= 0:
            continue
        # 행정 경계로 부지를 잘라내거나 중심점 반경으로 면적을 만들지 않는다.
        hits = [id for id,g in districts if g.covers(geom.representative_point())]
        if len(hits) != 1:
            raise ValueError('저류 영역 소속 구 확인 필요')
        identifier = ('way/'+props['osm_way_id']) if props.get('osm_way_id') else 'relation/'+props['osm_id']
        kept = {k:v for k,v in props.items() if k in ('name','landuse','natural','leisure') and v is not None}
        kept.update({k:v for k,v in tags.items() if k in ('basin','water','intermittent','layer','location','covered')})
        originals.append({'type':'Feature','id':identifier,'properties':kept,'geometry':feature['geometry']})
        asset_id = 'OSM_BASIN:'+identifier
        polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        point = geom.representative_point()
        footprint = {'polygons':[[list(map(list,poly.exterior.coords)),
            *[list(map(list,ring.coords)) for ring in poly.interiors]] for poly in polygons],
            'areaM2':geom.area,'sourceObjectUrl':'https://www.openstreetmap.org/'+identifier,
            'mappedAt':'2026-10-16','basinType':tags['basin'],
            'basis':'PUBLIC_OSM_MAPPING_NOT_SURVEYED_OR_AS_BUILT','policyVersion':VERSION}
        assets.append({'id':asset_id,'sourceId':'OSM_SEOUL_BASINS_20261016',
            'name':props.get('name') or '공개 지도 저류 영역 · '+identifier,
            'kind':'RETENTION_BASIN','center':[point.x,point.y],'districtId':hits[0],
            'displayStatus':'REFERENCE','geometryEvidence':'PUBLIC_MAPPED_FOOTPRINT',
            'verticalLayer':'MAPPED_SURFACE','validFrom':None,'validTo':None,'operationStatus':'UNKNOWN',
            'hydraulicStatus':'UNCONNECTED','sourceProperties':kept,'pumpSpecs':None,'footprint':footprint})
        shapes[asset_id]=geom
    assets.sort(key=lambda a:a['id']);originals.sort(key=lambda a:a['id'])
    derived = ROOT/f'data/derived/infrastructure/{VERSION}.geojson'
    derived_hash = save(derived,{'type':'FeatureCollection','features':originals})
    root = ROOT/'backend/src/main/resources/shared-sites'
    catalog_raw = (root/'catalog-v6.json').read_bytes()
    exclusions = []
    for entry in json.loads(catalog_raw)['entries']:
        compressed=(root/entry['file']).read_bytes();unpacked=gzip.decompress(compressed)
        if sha(compressed)!=entry['gzipSha256'] or sha(unpacked)!=entry['sha256']:
            raise ValueError('후보 원본 해시 불일치')
        for cell in json.loads(unpacked)['cells']:
            for asset in assets:
                area = overlap(cell,shapes[asset['id']])
                if area > 0:
                    exclusions.append({'districtId':entry['districtId'],'cellId':cell['id'],
                        'siteModelHash':entry['sha256'],'assetId':asset['id'],'assetName':asset['name'],
                        'overlapAreaM2':area})
    policy = {'version':VERSION,'sourceSha256':registry['sourceSha256'],
        'sourceExtractSha256':registry['extractHashes'][source.name], 'geometrySha256':derived_hash,
        'siteCatalogSha256':sha(catalog_raw),'coordinateSystem':'EPSG:5186_LOCAL',
        'scope':'CURRENT_MAPPED_GEOMETRY_NEW_GROUND_PLACEMENTS_ONLY',
        'historicalExistenceVerified':False,'exclusions':exclusions,'assets':assets}
    policy_hash = save(ROOT/f'backend/src/main/resources/infrastructure/{VERSION}.json',policy)
    old_path=ROOT/'backend/src/main/resources/infrastructure/seoul-public-20261018-v1.json'
    old_raw=old_path.read_bytes()
    if sha(old_raw)!='6b1ff662e040eca3d5da5cdc9ff5c58127bc14f0752f3ddd3ea9796debea79fb':
        raise ValueError('기존 공개 시설 카탈로그 변경')
    combined=json.loads(old_raw);combined['version']='seoul-public-20261018-v2'
    combined['assets']+=assets
    combined['sources'].append({'id':'OSM_SEOUL_BASINS_20261016','title':'서울 공개 지도 저류 영역',
        'publisher':'OpenStreetMap 기여자','url':'https://www.openstreetmap.org/copyright',
        'sha256':registry['sourceSha256'],'license':'ODbL-1.0','fileModifiedAt':'2026-10-16',
        'portalUpdatedAt':None,'referenceDate':'2026-10-16','retrievedAt':'2026-10-17',
        'crs':'EPSG:4326','records':len(assets)})
    catalog_hash=save(ROOT/'backend/src/main/resources/infrastructure/seoul-public-20261018-v2.json',combined)
    manifest={'version':VERSION,'generatorSha256':file_sha(Path(__file__)),
        'sourceManifestSha256':file_sha(ROOT/'data/manifests/seoul-city-v1.json'),
        'geometryPath':str(derived.relative_to(ROOT)),'geometrySha256':derived_hash,
        'policySha256':policy_hash,'catalogSha256':catalog_hash,'assets':len(assets),
        'excludedGroundSites':len(exclusions),'sourceUrl':registry['sourceUrl'],'license':'ODbL-1.0',
        'tagDefinitionUrls':['https://wiki.openstreetmap.org/wiki/Key:basin',
            'https://wiki.openstreetmap.org/wiki/Tag:landuse%3Dbasin'],
        'limitations':['공개 지도 분류·도형이며 준공/측량/현재 운전·용량 검증 아님',
            '이름만 유수지인 공원·주차장과 미분류 수면은 저류시설로 확정하지 않음',
            '지상 후보의 양의 교차 면적만 신규 설치 제외; 옥상·과거 설치 이력은 미변경',
            '실제 현장 저감 계산과 과거 재난 당시 자산 복원에 사용하지 않음']}
    save(ROOT/f'data/manifests/{VERSION}.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('policySha256','catalogSha256','assets','excludedGroundSites')}))


if __name__=='__main__':
    build()
