"""보관 지도에서 명시된 빗물펌프장 건물과 같은 원본의 후보 결속."""
import gzip
import json
import subprocess
from pathlib import Path

import pyproj
import shapely
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon, shape
from prepare_basin_footprints import ROOT, file_sha, save, sha

VERSION = 'seoul-pump-buildings-20261019-v1'
CATALOG = 'seoul-public-20261019-v3'
POLICY = 'seoul-infrastructure-occupancy-20261019-v5'


def build():
    registry = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_bytes())
    source = ROOT/registry['sourceDirectory']/'seoul-polygons.geojson'
    if file_sha(source) != registry['extractHashes'][source.name]:
        raise ValueError('보관 공개 지도 해시 불일치')
    raw = subprocess.run(['ogr2ogr','-f','GeoJSON','/vsistdout/',str(source),
        '-where',"building IS NOT NULL AND name LIKE '%빗물펌프장'"],
        check=True,capture_output=True,timeout=60).stdout
    city_raw = (ROOT/'frontend/public/data/seoul-v1/city.json').read_bytes()
    if sha(city_raw) != registry['city']['sha256']:
        raise ValueError('서울 지도 해시 불일치')
    districts = [(d['id'],MultiPolygon([Polygon(p[0],p[1:]) for p in d['polygons']]))
        for d in json.loads(city_raw)['districts']]
    root = ROOT/'backend/src/main/resources'
    catalog_raw = (root/'shared-sites/catalog-v9.json').read_bytes()
    candidates = {}
    for entry in json.loads(catalog_raw)['entries']:
        compressed = (root/'shared-sites'/entry['file']).read_bytes()
        unpacked = gzip.decompress(compressed)
        if sha(compressed)!=entry['gzipSha256'] or sha(unpacked)!=entry['sha256']:
            raise ValueError('후보 원본 해시 불일치')
        for cell in json.loads(unpacked)['cells']:
            for identifier in cell['sourceIds']:
                if cell['kind']=='ROOF': candidates.setdefault(identifier,[]).append((entry,cell))
    transform = pyproj.Transformer.from_crs(4326,5186,always_xy=True,allow_ballpark=False)
    assets, originals, exclusions = [], [], []
    for feature in json.loads(raw)['features']:
        p = feature['properties']; tags = p.get('other_tags') or {}
        if p['building'] in ('no','construction','roof') or any(k.startswith(('disused','abandoned','demolished','construction')) for k in tags):
            continue
        original = shape(feature['geometry'])
        if not original.is_valid or original.is_empty: raise ValueError('건물 원본 도형 오류')
        geometry = translate(shapely.transform(original,transform.transform,interleaved=False),-198128.,-551989.)
        hits = [id for id,g in districts if g.covers(geometry.representative_point())]
        if not hits: continue
        if len(hits)!=1: raise ValueError('소속 구 모호')
        identifier = 'way/'+p['osm_way_id'] if p.get('osm_way_id') else 'relation/'+p['osm_id']
        source_cells = candidates.get(identifier,[])
        if len(source_cells)!=1: raise ValueError('동일 원본 건물 후보 확인 필요')
        entry,cell = source_cells[0]
        # 근처 주소점 대신 같은 공개 원본 식별자와 도형 일치로 건물 후보를 결속한다.
        if entry['districtId']!=hits[0] or geometry.symmetric_difference(Polygon(cell['coordinates'])).area > 0.001:
            raise ValueError('같은 원본의 건물 도형 불일치')
        point = geometry.representative_point(); polys = list(geometry.geoms) if geometry.geom_type=='MultiPolygon' else [geometry]
        kept = {k:v for k,v in p.items() if v is not None}
        asset_id = 'OSM_PUMP_BUILDING:'+identifier
        assets.append(dict(id=asset_id, sourceId='OSM_SEOUL_PUMP_BUILDINGS_20261016',name=p['name'],kind='STORM_PUMP',
            center=[point.x,point.y],districtId=hits[0],displayStatus='REFERENCE',geometryEvidence='PUBLIC_MAPPED_BUILDING',
            verticalLayer='MAPPED_BUILDING',validFrom=None,validTo=None,operationStatus='UNKNOWN',hydraulicStatus='UNCONNECTED',
            sourceProperties=kept,pumpSpecs=None,footprint=dict(
                polygons=[[list(map(list,g.exterior.coords)),*[list(map(list,r.coords)) for r in g.interiors]] for g in polys],
                areaM2=geometry.area,sourceObjectUrl='https://www.openstreetmap.org/'+identifier,mappedAt='2026-10-16',
                buildingId=identifier.replace('way/','W').replace('relation/','R'),displayHeightM=cell['heightM'],
                heightBasis='EXISTING_CITY_DISPLAY_ASSUMPTION',basis='PUBLIC_OSM_MAPPING_NOT_SURVEYED_OR_AS_BUILT',policyVersion=VERSION)))
        originals.append(dict(type='Feature',id=identifier,properties=kept,geometry=feature['geometry']))
        exclusions.append(dict(districtId=hits[0],cellId=cell['id'],siteModelHash=entry['sha256'],siteKind='ROOF',
            assetId=asset_id,assetName=p['name'],overlapAreaM2=cell['areaM2'],
            basis='IDENTICAL_OSM_BUILDING_NEW_INSTALLATION_RESERVATION'))
    assets.sort(key=lambda a:a['id']);originals.sort(key=lambda a:a['id']);exclusions.sort(key=lambda a:a['assetId'])
    geometry_path = ROOT/f'data/derived/infrastructure/{VERSION}.geojson'
    geometry_hash = save(geometry_path,dict(type='FeatureCollection',features=originals))
    old_path = root/'infrastructure/seoul-public-20261018-v2.json';old_raw=old_path.read_bytes()
    if sha(old_raw)!='325bb73079cd70017a57a0d346e93c6f0a8376af181542dfa461fa746aa21764': raise ValueError('이전 카탈로그 변경')
    catalog = json.loads(old_raw);catalog['version']=CATALOG;catalog['assets']+=assets
    catalog['sources'].append(dict(id='OSM_SEOUL_PUMP_BUILDINGS_20261016',title='서울 공개 지도 빗물펌프장 건물',
        publisher='OpenStreetMap 기여자',url='https://www.openstreetmap.org/copyright',sha256=registry['sourceSha256'],license='ODbL-1.0',
        fileModifiedAt='2026-10-16',portalUpdatedAt=None,referenceDate='2026-10-16',retrievedAt='2026-10-17',crs='EPSG:4326',records=len(assets)))
    catalog_hash=save(root/f'infrastructure/{CATALOG}.json',catalog)
    old_policy=(root/'infrastructure/seoul-basin-footprints-20261018-v4.json').read_bytes()
    if sha(old_policy)!='5b15ba1ff3df4460f33a4bac3dd68485c082d7c56d75eec8653d8631444eb871': raise ValueError('이전 점유 정책 변경')
    policy=json.loads(old_policy)
    if policy['siteCatalogSha256']!=sha(catalog_raw): raise ValueError('후보 정책 버전 불일치')
    for row in policy['exclusions']:row['siteKind']='GROUND'
    policy.update(version=POLICY,previousPolicySha256=sha(old_policy),scope='CURRENT_MAPPED_GROUND_AND_RESERVED_BUILDINGS',
        buildingGeometrySha256=geometry_hash)
    policy['exclusions']+=exclusions;policy['assets']+=assets
    policy_hash=save(root/f'infrastructure/{POLICY}.json',policy)
    manifest=dict(version=VERSION,generatorSha256=file_sha(Path(__file__)),sourceManifestSha256=file_sha(ROOT/'data/manifests/seoul-city-v1.json'),
        sourceSha256=registry['sourceSha256'],sourceExtractSha256=registry['extractHashes'][source.name],geometryPath=str(geometry_path.relative_to(ROOT)),
        geometrySha256=geometry_hash,catalogSha256=catalog_hash,policySha256=policy_hash,buildingCount=len(assets),reservedRoofCandidates=len(exclusions),
        sourceUrl=registry['sourceUrl'],license='ODbL-1.0',
        definitions=['https://wiki.openstreetmap.org/wiki/Tag:man_made%3Dpumping_station','https://wiki.openstreetmap.org/wiki/Key:building'],
        limitations=['공개 지도 건물 분류·명칭·경계이며 현장/준공 검증 아님','신규 게임 설치의 건물 예약 규칙이며 옥상에 물리적으로 펌프가 있다는 뜻 아님',
        '높이는 기존 도시 표시용 가정; 시설 내부 치수·용량·운영·존속 시점 미확인','기존 공식 위치점과 합병하지 않으며 과거 자료·설치 기록 보존','현재 물리 계산과 당시 재해 자산 입력에 포함하지 않음'])
    save(ROOT/f'data/manifests/{VERSION}.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('catalogSha256','policySha256','buildingCount','reservedRoofCandidates')}))

if __name__=='__main__':build()
