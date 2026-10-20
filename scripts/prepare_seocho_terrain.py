"""서초 공개 등고선·표고점의 계산 지형과 원 관망 높이 대조."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import quote

import shapely
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))

from topography_catalog import SpatialCatalog
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.published_network import load_archive, inspect_input
from waterleague_sim.terrain.contours import ContourTin, METHOD, residual_summary, surface_from_contours
from waterleague_sim.terrain.grid import digest

GEOREFERENCE = ROOT/'backend/src/main/resources/watersheds/seocho-georeference-v1.json'
GEOREFERENCE_SHA = '36a477f877d0d0fc4518f5e7664497e6e36798299745880932d5b43148ac01ab'
SPATIAL = ROOT/'data/manifests/seoul-spatial-catalog-v1.json'
NETWORK = ROOT/'backend/src/main/resources/watersheds/seocho-published-v1.json'
NETWORK_SHA = 'beaddba8868b6f1f6bbf35b1d53d4695a94db99498d8988f90d62013cf8f053c'
NETWORK_SOURCE = ROOT/'data/manifests/mendeley-seocho-network-v3.json'
LAYERS = ['N1L_F0010000', 'N1P_F0020000']
SOURCE_BUFFER = 500.
DOMAIN_BUFFER = 100.
SPACINGS = (20., 10.)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(',', ':'), allow_nan=False)+'\n')


def vertical_reference():
    return {'unit': 'm', 'unitStatus': 'PRODUCT_FAMILY_INFERRED', 'datum': None, 'datumVerified': False,
        'unitEvidence': {'accessedOn': '2026-10-21', 'sources': [
            {'url': 'https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2000000085686',
             'title': '공공측량 작업규정 과거본의 표고점 미터 단위 표기',
             'use': '제품군 단위 해석; 현행 규정 준수 또는 배포 파일의 직접 메타데이터 아님'},
            {'url': 'https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000272806&chrClsCd=010201',
             'title': '수치표고모형의 구축 및 관리 등에 관한 규정', 'version': '2026-283, 2026-01-13',
             'section': '제43조 제1항', 'use': '표고모형 미터 좌표 표기; 본 파생물의 측량 정확도 인증 아님'}],
            'limitation': '수치지형도 DBF 높이의 제품군 미터 해석; 해당 도엽 수직 기준·측정 시점 미확인'}}


def excluded(spatial, bounds):
    uri = 'file:'+quote(str(spatial.database))+'?mode=ro&immutable=1'
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.execute('PRAGMA trusted_schema=OFF')
        conn.execute('PRAGMA query_only=ON')
        rows = conn.execute('''SELECT tile,layer,record_number,geometry_status,geometry_detail,
            deleted,raw_shape_sha256,raw_dbf_sha256 FROM features
            WHERE layer IN (?,?) AND (geometry_status!='VALID' OR deleted!=0)
            AND (minx IS NULL OR (maxx>=? AND minx<=? AND maxy>=? AND miny<=?))
            ORDER BY tile,layer,record_number''', (*LAYERS, bounds[0], bounds[2], bounds[1], bounds[3])).fetchall()
    return [dict(zip(('tile', 'layer', 'recordNumber', 'geometryStatus', 'geometryDetail',
                     'deleted', 'sourceShapeSha256', 'sourceDbfSha256'), row, strict=True)) for row in rows]


def contour_residuals(tin):
    rows = []
    for record in tin.records:
        if record['role'] != 'CONTOUR_LINE':
            continue
        geometry = shape(record['geometry'])
        parts = list(geometry.geoms) if geometry.geom_type == 'MultiLineString' else [geometry]
        source_z = float(record['attributes']['등고수치'])
        for part_index, part in enumerate(parts):
            coordinates = list(part.coords)
            for i, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
                xy = [(x+y)/2 for x, y in zip(a, b, strict=True)]
                sample = tin.sample(xy)
                rows.append({'recordId': record['id'], 'part': part_index, 'segment': i,
                    'coordinate': xy, 'sourceHeightM': source_z,
                    'differenceM': sample['heightM']-source_z if sample else None})
    return rows


def spot_residuals(tin, records):
    rows = []
    for record in records:
        if record['role'] == 'ELEVATION_POINT':
            xy = list(shape(record['geometry']).coords[0])
            sample = tin.sample(xy)
            z = float(record['attributes']['수치'])
            rows.append({'recordId': record['id'], 'coordinate': xy, 'sourceHeightM': z,
                         'sample': sample, 'differenceM': sample['heightM']-z if sample else None})
    return rows


def hydraulic_specification(count):
    return {'maxStepSeconds': 1., 'manningN': [.011]*count, 'initialDepthM': [0.]*count,
        'rainfallOwner': ['SURFACE']*count,
        'boundaryConditions': {key: {'type': 'TRANSMISSIVE'} for key in ('north', 'south', 'east', 'west')},
        'evidence': {'roughness': '원 연구 SWMM의 불투수면 Manning n=0.011을 전 영역에 적용한 민감도 기준; 실제 혼합 피복 아님',
            'initialState': '건조 초기 상태의 입력 검증; 선행 강우 상태 미적용',
            'boundary': '유역 표시 범위 주변 100m 사각 창의 전달 경계; 실제 분수계·하천 수위 아님',
            'rainfallOwner': '지형 입력 단독 검증의 직접 강우; 관망 소유 면적과 아직 결합하지 않음'}}


def prepare(directory):
    directory = Path(directory).absolute()
    require(directory.resolve() == directory and not directory.exists(), 'SEOCHO_TERRAIN_OUTPUT_INVALID')
    require(sha(GEOREFERENCE) == GEOREFERENCE_SHA and sha(NETWORK) == NETWORK_SHA,
            'SEOCHO_TERRAIN_SOURCE_CHANGED')
    location = json.loads(GEOREFERENCE.read_bytes())
    catalog = json.loads(NETWORK.read_bytes())
    metadata = json.loads(SPATIAL.read_bytes())
    require(location['horizontalCrs'] == metadata['coordinateSystem'] == 'EPSG:5186'
            and location['sourceCrsVerified'] is False and location['verticalDatum'] is None,
            'SEOCHO_TERRAIN_REFERENCE_CHANGED')
    spatial = SpatialCatalog(ROOT/metadata['localCatalogDirectory'], metadata)
    b = location['bounds']
    bounds = [b[0]-SOURCE_BUFFER, b[1]-SOURCE_BUFFER, b[2]+SOURCE_BUFFER, b[3]+SOURCE_BUFFER]
    omitted = excluded(spatial, bounds)
    require(not omitted, 'SEOCHO_TERRAIN_SOURCE_EXCLUSIONS')
    source_records = [dict(row, geometry=mapping(row['geometry']))
                      for row in spatial.query(bounds, layers=LAYERS)]
    tin = ContourTin(source_records)
    records = tin.records
    contours_only = ContourTin([r for r in records if r['role'] == 'CONTOUR_LINE'])
    line_checks = contour_residuals(tin)
    point_checks = spot_residuals(contours_only, records)
    require(all(r['differenceM'] is not None for r in line_checks), 'SEOCHO_TERRAIN_CONTOUR_UNSUPPORTED')
    _, source_hash, entries = load_archive(ROOT, NETWORK_SOURCE)
    require(source_hash == catalog['sourceManifestSha256'], 'SEOCHO_TERRAIN_NETWORK_CHANGED')
    original = next(e['raw'] for e in entries if e['member'] == catalog['sourceMember'])
    require(hashlib.sha256(original).hexdigest() == location['sourceOriginalSha256']
            == catalog['sourceOriginalSha256'], 'SEOCHO_TERRAIN_NETWORK_CHANGED')
    network = inspect_input(original)
    require(network['options']['FLOW_UNITS'] == 'CMS'
            and all(float(r['tokens'][1]) == .011 for r in network['sourceRecords']['SUBAREAS']),
            'SEOCHO_TERRAIN_ROUGHNESS_SOURCE_CHANGED')
    nodes = {n['id']: n for n in network['nodes']}
    require(set(nodes) == {n['id'] for n in location['nodes']}, 'SEOCHO_TERRAIN_NODES_CHANGED')
    comparison = []
    for row in location['nodes']:
        n = nodes[row['id']]
        sample = tin.sample(row['coordinate'])
        require(sample is not None, 'SEOCHO_TERRAIN_NODE_UNSUPPORTED')
        rim = n['invertDeclared']+float(n['parameters'][0]) if n['kind'] == 'JUNCTION' else None
        comparison.append({**row, 'surface': sample, 'sourceInvertM': n['invertDeclared'],
            'sourceRimM': rim, 'surfaceMinusRimM': sample['heightM']-rim if rim is not None else None,
            'surfaceMinusInvertM': sample['heightM']-n['invertDeclared'],
            'verticalDatumAgreementVerified': False, 'appliedHeightAdjustmentM': 0.})
    # 해상도 비교에서 외곽 경계의 이동 효과가 섞이지 않도록 같은 창을 사용한다.
    domain = [math.floor((b[0]-DOMAIN_BUFFER)/20)*20., math.floor((b[1]-DOMAIN_BUFFER)/20)*20.,
              math.ceil((b[2]+DOMAIN_BUFFER)/20)*20., math.ceil((b[3]+DOMAIN_BUFFER)/20)*20.]
    directory.mkdir(parents=True)
    sources = [GEOREFERENCE, NETWORK, NETWORK_SOURCE, SPATIAL, Path(__file__),
               ROOT/'scripts/topography_catalog.py', ROOT/'scripts/prepare_seoul_topography.py',
               ROOT/'simulation/waterleague_sim/terrain/contours.py',
               ROOT/'simulation/waterleague_sim/terrain/grid.py', ROOT/'simulation/uv.lock',
               ROOT/'simulation/pyproject.toml']
    source_files = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    source_files['data/private/vworld-seoul-topography-20260307/spatial-v1/spatial.sqlite'] = metadata['spatialSha256']
    for path in sources:
        target = directory/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    write(directory/'source-records.json', records)
    write(directory/'tin.json', tin.describe())
    write(directory/'contour-midpoint-residuals.json', line_checks)
    write(directory/'excluded-spot-residuals.json', point_checks)
    (directory/'original-network.inp').write_bytes(original)
    grids = []
    for spacing in SPACINGS:
        grid = tin.grid(domain, spacing, source_files, vertical_reference())
        specification = hydraulic_specification(2*(grid['width']-1)*(grid['height']-1))
        model = surface_from_contours(grid, specification)
        key = f'{int(spacing)}m'
        write(directory/f'grid-{key}.json', grid)
        write(directory/f'specification-{key}.json', specification)
        write(directory/f'surface-{key}.json', model)
        grids.append({'spacingM': spacing, 'width': grid['width'], 'height': grid['height'],
            'triangles': len(model['triangles']), 'gridSha256': sha(directory/f'grid-{key}.json'),
            'surfaceSha256': sha(directory/f'surface-{key}.json'),
            'heightRangeM': [min(grid['values']), max(grid['values'])]})
    report = {'schemaVersion': 1, 'method': METHOD, 'rankingEligible': False,
        'classification': 'PUBLIC_CONTOUR_TIN_EXPLORATORY_NOT_SITE_VALIDATED',
        'horizontalCrs': 'EPSG:5186', 'georeferenceSha256': GEOREFERENCE_SHA,
        'verticalReference': vertical_reference(), 'absoluteVerticalReferenceVerified': False,
        'sourceCatalogSha256': metadata['spatialSha256'], 'queryBounds': bounds,
        'sourceBufferM': SOURCE_BUFFER, 'domainBufferM': DOMAIN_BUFFER, 'domainBounds': domain,
        'areaM2': (domain[2]-domain[0])*(domain[3]-domain[1]),
        'sourceCounts': {role: sum(r['role'] == role for r in records) for role in ('CONTOUR_LINE', 'ELEVATION_POINT')},
        'excludedRecords': omitted, 'uniqueControlPoints': tin.original_point_count,
        'derivedContourPoints': len(tin.points)-tin.original_point_count,
        'refinement': tin.refinement, 'tinTriangles': len(tin.triangles),
        'tinSha256': tin.identity, 'sourceRecordsSha256': digest(records), 'grids': grids,
        'contourMidpointResidual': residual_summary(line_checks),
        'excludedSpotResidual': residual_summary(point_checks), 'networkComparison': comparison,
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources if p.suffix == '.py'},
        'limitations': model['terrainProvenance']['limitations']+[
            '표고점 제외 검사는 같은 배포 자료의 내부 대조이며 독립 현장 검증 아님',
            '원 관망 높이·단면·강우·외부 유입을 변경하지 않음',
            '방류구는 자유 방류 연구 경계이며 위치의 지표 높이와 일치한다고 가정하지 않음',
            '실제 지표·관망 결합, 토지피복, 강우 소유 면적 및 게임 결과 통합은 후속 계산에 필요']}
    report['files'] = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'manifest.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.output)
    print(json.dumps({k: report[k] for k in ('sourceCounts', 'uniqueControlPoints', 'tinTriangles',
                     'grids', 'contourMidpointResidual', 'excludedSpotResidual')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
