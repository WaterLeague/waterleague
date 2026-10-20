"""공개 원 시설 위치점의 행정구·원형 후보 대응. 부지·수직 위치 추정 금지."""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import shutil
import zipfile

import pyproj
from shapely.geometry import Point, shape

import prepare_public_infrastructure as original
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from waterleague_sim.spatial import play_bundle, play_catalog
from waterleague_sim.spatial.play_bundle import open_catalog

VERSION = 'seoul-native-infrastructure-20261020-v1'
BOUNDARIES = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'
BOUNDARY_SHA256 = 'ff49da7030e1abcea4190aa3e3375714889fc537c2759cb4d220c04e764cf4c4'
ORIGIN = [198128, 551989]
OUTPUT = source.ROOT / 'backend/src/main/resources/infrastructure/native-v1'
CRS_EVIDENCE = source.ROOT / 'data/derived/seoul-infrastructure-crs-v1.json'
CRS_EVIDENCE_SHA256 = 'b49211c717e788ac0e23f3e41128c1bb895ffad1bcc6638949a41e3c3948977b'


def build(output):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise ValueError('기존 시설 출력·링크 덮어쓰기 금지')
    with source.source_stream(BOUNDARIES, expected_sha256=BOUNDARY_SHA256) as (stream, _):
        boundaries = json.load(stream)
    with source.source_stream(CRS_EVIDENCE, expected_sha256=CRS_EVIDENCE_SHA256) as (stream, _):
        crs_sources = {row['datasetId']: row for row in json.load(stream)['sources']}
    districts = [(row['id'], shape(row['nativeGeometry'])) for row in boundaries['districts']]
    code_hashes = {str(Path(module.__file__).resolve().relative_to(source.ROOT)): spatial.file_sha256(module.__file__)
        for module in (original, source, spatial, play_bundle, play_catalog)}
    code_sha = spatial.file_sha256(__file__)
    inputs = {str(BOUNDARIES.relative_to(source.ROOT)): BOUNDARY_SHA256}
    inputs[str(CRS_EVIDENCE.relative_to(source.ROOT))] = CRS_EVIDENCE_SHA256
    assets, sources = [], []

    def record(m, record_id, title, kind, xy, deletion, properties, deletion_field=True):
        if len(xy) != 2 or any(not math.isfinite(value) for value in xy):
            raise ValueError('시설 위치점 좌표 오류')
        center = [xy[i] - ORIGIN[i] for i in (0, 1)]
        if any(abs(value) >= 60000 for value in center):
            raise ValueError('시설 위치점 범위 오류')
        hits = [identifier for identifier, geometry in districts if geometry.covers(Point(xy))]
        district = hits[0] if len(hits) == 1 else None
        return dict(id=f'{m["datasetId"]}:{record_id}', sourceId=m['datasetId'], name=title,
            kind=kind, center=center, districtId=district,
            displayStatus=original.display_status(deletion, district, deletion_field),
            geometryEvidence='LOCATION_POINT', verticalLayer='UNKNOWN', validFrom=None, validTo=None,
            operationStatus='UNKNOWN', hydraulicStatus='UNCONNECTED', sourceProperties=properties,
            pumpSpecs=None, footprint=None)

    for manifest_name, title, kind in original.SOURCES:
        manifest_path = source.ROOT / 'data/manifests' / (manifest_name + '.json')
        with source.source_stream(manifest_path) as (stream, checksum):
            manifest = json.load(stream)
        inputs[str(manifest_path.relative_to(source.ROOT))] = checksum
        path, raw = original.raw_source(manifest, False)
        inputs[str(path.relative_to(source.ROOT))] = manifest['sha256']
        count = len(assets)
        if path.suffix == '.csv':
            transform = pyproj.Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
            for name, group in sorted(original.grouped_pumps(raw).items()):
                row = group['row']
                xy = transform.transform(float(row['경도']), float(row['위도']))
                item = record(manifest, name, name + ' 빗물펌프장', kind, xy, None, row, False)
                item['pumpSpecs'] = dict(asOf=row['데이터기준일자'], address=row['펌프장 주소'],
                    basinAreaHa=float(row['유역면적(ha)']), storageCapacityM3=float(row['유수지 용량(세제곱미터)']),
                    units=sorted(group['units'], key=lambda value: value['unit']))
                assets.append(item)
        else:
            with zipfile.ZipFile(path) as archive:
                references = [name for name in archive.namelist() if name.lower().endswith('.prj')]
                if len(references) > 1 or (references and not pyproj.CRS.from_wkt(archive.read(references[0]).decode('utf-8-sig')).equals(
                        pyproj.CRS.from_epsg(5186), ignore_axis_order=True)):
                    raise ValueError('공개 시설 원 좌표계 불일치')
                if not references and crs_sources[manifest['datasetId']]['providerDeclaredCrs'] != 'EPSG:5186':
                    raise ValueError('공개 시설의 공식 좌표계 선언 누락')
            for feature in original.read_shape(path):
                geometry, props = feature['geometry'], feature['properties']
                if geometry['type'] != 'MultiPoint' or len(geometry['coordinates']) != 1:
                    raise ValueError('공개 시설 원 위치점 형식 오류')
                name = props['PUMP_NM'] + ' 빗물펌프장' if props.get('PUMP_NM') else title + ' · 등록 ' + str(props.get('REGSTR_NO', props['OBJECTID']))
                assets.append(record(manifest, str(props['OBJECTID']), name, kind,
                    geometry['coordinates'][0], props.get('DEL_YN'), props, kind != 'STORM_PUMP'))
        sources.append(dict(id=manifest['datasetId'], title=title,
            publisher='서울특별시 강서구' if path.suffix == '.csv' else '서울특별시',
            url=manifest['sourceUrl'], sha256=manifest['sha256'], license='KOGL_TYPE_1',
            fileModifiedAt=manifest.get('fileModifiedAt'), portalUpdatedAt=manifest.get('portalUpdatedAt'),
            referenceDate='2025-09-08' if path.suffix == '.csv' else None,
            crs='EPSG:4326' if path.suffix == '.csv' else 'EPSG:5186',
            crsBasis='PUBLIC_LONGITUDE_LATITUDE_FIELDS' if path.suffix == '.csv' else 'PROVIDER_DECLARATION_PRJ_NOT_INCLUDED',
            retrievedAt=manifest['retrievedAt'], records=len(assets) - count))
    if len({asset['id'] for asset in assets}) != len(assets):
        raise ValueError('공개 시설 식별자 중복')
    catalog = dict(version=VERSION, origin=ORIGIN, coordinateSystem='EPSG:5186_LOCAL',
        boundarySha256=BOUNDARY_SHA256, sources=sources, assets=sorted(assets, key=lambda asset: asset['id']))
    catalog_raw = (source.canonical(catalog) + '\n').encode()
    play = open_catalog()
    associations = []
    for asset in catalog['assets']:
        if asset['displayStatus'] != 'REFERENCE':
            continue
        x, y = [asset['center'][i] + ORIGIN[i] for i in (0, 1)]
        for cell in play.bounds([x - 1e-6, y - 1e-6, x + 1e-6, y + 1e-6], limit=2000):
            if shape(cell['geometry']).covers(Point(x, y)):
                associations.append(dict(assetId=asset['id'], assetName=asset['name'], districtId=cell['districtId'],
                    cellId=cell['id'], siteModelHash=play.sha256, relation='PUBLIC_POINT_COVERED_BY_NATIVE_CANDIDATE',
                    verticalLayer='UNKNOWN', footprintVerified=False))
    policy = dict(version=VERSION, sourceSha256=source.digest(catalog_raw), siteCatalogSha256=play.sha256,
        coordinateSystem='EPSG:5186', scope='CURRENT_NATIVE_POINT_ASSOCIATIONS_REFERENCE_ONLY',
        historicalExistenceVerified=False, exclusions=[],
        associations=sorted(associations, key=lambda row: (row['districtId'], row['cellId'], row['assetId'])),
        limitations=['공개 위치점과 후보의 수평 포함 관계이며 시설 부지·수직 위치·운영 상태 미확인',
            '위치점만으로 후보 전체를 시설 부지로 채우거나 면적 중첩·시공 적합성을 확정하지 않음'])
    output.mkdir()
    try:
        hashes = {}
        for name, value in [('catalog.json', catalog), ('associations.json', policy)]:
            raw = (source.canonical(value) + '\n').encode()
            with (output / name).open('xb') as target:
                target.write(raw)
            hashes[name] = source.digest(raw)
        if spatial.file_sha256(__file__) != code_sha or any(spatial.file_sha256(source.ROOT / name) != sha
                for name, sha in (inputs | code_hashes).items()):
            raise ValueError('공개 시설 생성 중 입력·코드 변경')
        summary = dict(schemaVersion=1, version=VERSION, generatorSha256=code_sha, sourceHashes=inputs,
            implementationHashes=code_hashes, versions={'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str},
            files=hashes, assetCount=len(assets), pointAssociationCount=len(associations), confirmedFootprintCount=0,
            statusCounts=dict(sorted(Counter(asset['displayStatus'] for asset in assets).items())))
        (output / 'summary.json').write_text(source.canonical(summary) + '\n')
        return summary
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        value = build(args.output.absolute())
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, '공개 시설 원형 연결 실패: 원본·좌표계·출력 확인 필요\n')
    print(source.canonical({key: value[key] for key in ('assetCount', 'pointAssociationCount', 'files')}))


if __name__ == '__main__':
    main()
