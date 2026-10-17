"""공개 피복과 배치 구역의 좌표·면적 정합 검사. 운영 모델 변경 없음."""
import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import GeometryCollection, Polygon, mapping, shape
from shapely.ops import unary_union

import audit_spatial_sources as audit
import diagnose_landcover_topology as topology

METHODS = ('originalValidOnly', *topology.METHODS)
EMPTY = GeometryCollection()


def polygon(geometry, require_valid=False):
    if (geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty
            or shapely.get_coordinate_dimension(geometry) != 2
            or not all(math.isfinite(v) for point in shapely.get_coordinates(geometry) for v in point)
            or (require_valid and (not geometry.is_valid or geometry.area <= 0))):
        raise audit.SpatialDataError('유한한 2차원 면적 폴리곤 필요')
    return geometry


def ring(value):
    if (not isinstance(value, list) or not 4 <= len(value) <= 100_000
            or any(not isinstance(p, (list, tuple)) or len(p) != 2
                   or any(type(v) not in (float, int) or not math.isfinite(v) for v in p)
                   for p in value) or list(value[0]) != list(value[-1])):
        raise audit.SpatialDataError('닫힌 2차원 좌표 링 필요')
    return polygon(Polygon(value), True)


def cell_boundaries(model, snapshot, transformer):
    before = topology.json_hash([model, snapshot])
    if model['geometrySourceHash'] != snapshot['sourceHash']:
        raise audit.SpatialDataError('모델과 지도 원본 연결 불일치')
    origin = snapshot['origin']
    if (not isinstance(origin, list) or len(origin) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin)):
        raise audit.SpatialDataError('화면 투영 원점 형식 오류')
    lon0, lat0 = origin
    if not (-180 < lon0 < 180 and -85 < lat0 < 85):
        raise audit.SpatialDataError('지원하지 않는 화면 투영 원점')
    scale_x, scale_y = 111320 * math.cos(math.radians(lat0)), 111320
    buildings = [f for f in snapshot['features'] if f['kind'] == 'building']
    by_id = {f['id']: f for f in buildings}
    if len(by_id) != len(buildings) or not 1 <= len(model['cells']) <= 1000:
        raise audit.SpatialDataError('중복 건물 또는 배치 구역 수 오류')
    output, ids, roof_ids = [], set(), set()
    geod = pyproj.Geod(ellps='WGS84')
    for cell in model['cells']:
        identifier = cell['id']
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise audit.SpatialDataError('배치 구역 식별자 오류')
        ids.add(identifier)
        display = ring(cell['coordinates'])
        if type(cell['areaM2']) not in (float, int) or not math.isfinite(cell['areaM2']) or cell['areaM2'] <= 0:
            raise audit.SpatialDataError('모델 면적 오류')
        source = {'areaEvidence': cell['areaEvidence'], 'eligibilityEvidence': cell['eligibilityEvidence']}
        if cell['kind'] == 'ROOF':
            building = by_id.get(cell.get('buildingId'))
            if (building is None or building['id'] in roof_ids
                    or cell['coordinates'] != building['coordinates']
                    or cell['areaEvidence'] != 'OSM_WGS84_GEODESIC'):
                raise audit.SpatialDataError('옥상과 OSM 건물 연결 오류')
            roof_ids.add(building['id'])
            geographic = building['geographicCoordinates']
            ring(geographic)
            source.update(route='OSM_ORIGINAL_WGS84', buildingId=building['id'],
                          osmVersion=building['osmVersion'], sourceUpdatedAt=building['sourceUpdatedAt'])
            projected = [[round((x-lon0)*scale_x, 3), round((y-lat0)*scale_y, 3)] for x, y in geographic]
            if projected != cell['coordinates']:
                raise audit.SpatialDataError('OSM 원형상과 화면 좌표 불일치')
        elif cell['kind'] == 'GROUND':
            if (cell['areaEvidence'] != 'ASSUMED_EXPERIMENTAL_PATCH'
                    or cell['eligibilityEvidence'] != 'ASSUMED_LANDCOVER_NOT_SURVEYED'
                    or not display.equals(display.envelope) or display.area != 100
                    or display.bounds[2]-display.bounds[0] != 10
                    or display.bounds[3]-display.bounds[1] != 10 or cell['areaM2'] != 100):
                raise audit.SpatialDataError('가정된 지상 구역 규약 불일치')
            geographic = [[lon0+x/scale_x, lat0+y/scale_y] for x, y in cell['coordinates']]
            source.update(route='ASSUMED_DISPLAY_PATCH_INVERSE', surveyedBoundary=False,
                          origin=snapshot['origin'], displayRoundingDecimals=3,
                          inverseFormula='lon=lon0+x/(111320*cos(lat0)); lat=lat0+y/111320; lat0 in radians for cos')
        else:
            raise audit.SpatialDataError('지원하지 않는 배치 구역 유형')
        ring(geographic)
        if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in geographic):
            raise audit.SpatialDataError('WGS84 좌표 범위 오류')
        longitude, latitude = zip(*geographic)
        geodesic_area = abs(geod.polygon_area_perimeter(longitude, latitude)[0])
        if cell['kind'] == 'ROOF' and round(geodesic_area, 2) != cell['areaM2']:
            raise audit.SpatialDataError('옥상 지오데식 면적과 모델 면적 불일치')
        x, y = transformer.transform(longitude, latitude, errcheck=True)
        native = polygon(Polygon(zip(x, y)), True)
        output.append({'id': identifier, 'kind': cell['kind'], 'boundary': native,
                       'geometry': mapping(native), 'coordinateSource': source,
                       'modelAreaM2': cell['areaM2'], 'displayAreaM2': display.area,
                       'wgs84GeodesicAreaM2': geodesic_area, 'nativeAreaM2': native.area,
                       'nativeMinusModelAreaM2': native.area-cell['areaM2'],
                       'edgeTransform': 'ORIGINAL_VERTICES_WITH_STRAIGHT_NATIVE_SEGMENTS'})
    if topology.json_hash([model, snapshot]) != before:
        raise audit.SpatialDataError('좌표 연결 중 입력 변형')
    return output


class CoverageIndex:
    def __init__(self, features):
        if not isinstance(features, list) or len(features) > 100_000:
            raise audit.SpatialDataError('피복 도형 수 오류')
        self.source_hash = topology.json_hash(features)
        self.records, self.invalid, self.candidates = [], [], {m: [] for m in METHODS}
        for index, feature in enumerate(features):
            properties = feature.get('properties', {})
            code, name, captured = (properties.get(k) for k in ('L3_CODE', 'L3_NAME', 'IMG_DATE'))
            if (not isinstance(code, str) or not re.fullmatch(r'[0-9]{3}', code)
                    or not isinstance(name, str) or not name.strip() or '\ufffd' in name):
                raise audit.SpatialDataError('피복 분류 코드·명칭 오류')
            if captured not in (None, ''):
                try:
                    if not isinstance(captured, str) or date.fromisoformat(captured).isoformat() != captured:
                        raise ValueError()
                except ValueError as exc:
                    raise audit.SpatialDataError('피복 영상 날짜 형식 오류') from exc
            original = polygon(shape(feature['geometry']))
            record = {'featureIndex': index, 'classCode': code, 'className': name,
                      'imageDate': captured, 'propertiesSha256': topology.json_hash(properties),
                      'originalWkbSha256': topology.geometry_hash(original),
                      'originalValid': bool(original.is_valid)}
            self.records.append(record)
            self.candidates['originalValidOnly'].append(original if original.is_valid else EMPTY)
            invalid = {'featureIndex': index, 'envelope': original.envelope,
                       'reason': shapely.is_valid_reason(original), 'methods': {}}
            for method in topology.METHODS:
                candidate = original
                if not original.is_valid:
                    fixed = shapely.make_valid(original, method=method, keep_collapsed=True)
                    candidate = topology.polygonal(fixed)
                    if not candidate.is_valid or not fixed.is_valid:
                        raise audit.SpatialDataError('피복 보정 후보 유효성 오류')
                    invalid['methods'][method] = {'full': topology.describe(fixed),
                                                  'area': topology.describe(candidate)}
                self.candidates[method].append(candidate)
            if not original.is_valid:
                self.invalid.append(invalid)
        self.trees = {m: shapely.STRtree(gs) for m, gs in self.candidates.items()}

    def measure(self, boundary, method):
        clips, class_clips, intersections = [], defaultdict(list), []
        # 공간 인덱스 반환 순서는 의미가 없으므로 원본 순번으로 고정.
        for i in sorted(map(int, self.trees[method].query(boundary, predicate='intersects'))):
            geometry = self.candidates[method][i]
            clip = geometry.intersection(boundary)
            if clip.area <= 0:
                continue
            clips.append(clip)
            record = self.records[i]
            class_clips[record['classCode']].append(clip)
            intersections.append({**record, 'intersectionAreaM2': clip.area,
                                  'candidateWkbSha256': topology.geometry_hash(geometry)})
        merged = unary_union(clips)
        unions = {code: unary_union(parts) for code, parts in sorted(class_clips.items())}
        summed = math.fsum(c.area for c in clips)
        classes = {code: {'sumAreaM2': math.fsum(c.area for c in class_clips[code]),
                          'unionAreaM2': geometry.area,
                          'overlapAreaM2': math.fsum(c.area for c in class_clips[code])-geometry.area}
                   for code, geometry in unions.items()}
        return {'featureCount': len(intersections), 'sumAreaM2': summed, 'unionAreaM2': merged.area,
                'overlapAreaM2': summed-merged.area, 'uncoveredAreaM2': boundary.difference(merged).area,
                'coveredFraction': merged.area/boundary.area,
                'crossClassOverlapAreaM2': math.fsum(g.area for g in unions.values())-merged.area,
                'classes': classes, 'intersections': intersections}, merged, unions


def diagnose(features, cells, study):
    polygon(study, True)
    if not cells or len(cells) > 1000 or len({c['id'] for c in cells}) != len(cells):
        raise audit.SpatialDataError('배치 구역 수·식별자 오류')
    boundaries = [polygon(c['boundary'], True) for c in cells]
    index = CoverageIndex(features)
    report = {'status': 'DIAGNOSTIC_ONLY', 'modelEligible': False, 'calibrationEligible': False,
              'featuresSha256': index.source_hash, 'sourceFeatureCount': len(features),
              'originalInvalidCount': len(index.invalid), 'cells': [], 'placementOverlaps': [],
              'invalidSourceCandidates': [{k: v for k, v in item.items() if k != 'envelope'}
                                          for item in index.invalid]}
    for cell, boundary in zip(cells, boundaries):
        methods, unions, classes = {}, {}, {}
        for method in METHODS:
            methods[method], unions[method], classes[method] = index.measure(boundary, method)
        left, right = classes['linework'], classes['structure']
        nearby = [item for item in index.invalid if item['envelope'].intersects(boundary)]
        report['cells'].append({k: v for k, v in cell.items() if k != 'boundary'} | {
            'nativeAreaM2': boundary.area, 'outsideStudyAreaM2': boundary.difference(study).area,
            'numericAreaToleranceM2': max(1e-8, boundary.area*1e-10),
            'invalidEnvelopeIndexes': [item['featureIndex'] for item in nearby],
            'repairedPositiveAreaIndexes': {method: [r['featureIndex']
                for r in methods[method]['intersections'] if not r['originalValid']]
                for method in topology.METHODS}, 'methods': methods,
            'methodComparison': {
                'unionSymmetricDifferenceM2': unions['linework'].symmetric_difference(unions['structure']).area,
                'classSymmetricDifferenceM2': {code: left.get(code, EMPTY).symmetric_difference(
                    right.get(code, EMPTY)).area for code in sorted(left.keys() | right.keys())}}})
    for i, left in enumerate(boundaries):
        for j in range(i+1, len(boundaries)):
            overlap = left.intersection(boundaries[j]).area
            if overlap > 0:
                report['placementOverlaps'].append({'left': cells[i]['id'], 'right': cells[j]['id'],
                                                     'areaM2': overlap})
    report['placementAreaSumM2'] = math.fsum(b.area for b in boundaries)
    report['placementAreaUnionM2'] = unary_union(boundaries).area
    report['numericToleranceMeaning'] = '부동소수 집계 표시용; 원자료/변환 정확도나 측량 허용오차가 아님'
    if index.source_hash != topology.json_hash(features):
        raise audit.SpatialDataError('검사 중 피복 원본 변형')
    return report


def compare_buildings(cells, snapshot, transformer):
    geometries = []
    for building in snapshot['buildings']:
        geometry = polygon(shape({'type': 'MultiPolygon', 'coordinates': building['polygons']}), True)
        if any(not (127.04 <= x <= 127.07 and 37.53 <= y <= 37.56)
               for x, y in shapely.get_coordinates(geometry)):
            raise audit.SpatialDataError('수치지도 경계 좌표 범위 오류')
        geometries.append(polygon(shapely.transform(geometry, transformer.transform, interleaved=False), True))
    tree = shapely.STRtree(geometries)
    results = {}
    for cell in cells:
        intersections = []
        for i in sorted(map(int, tree.query(cell['boundary'], predicate='intersects'))):
            clip = geometries[i].intersection(cell['boundary'])
            if clip.area > 0:
                intersections.append((i, clip))
        union = unary_union([geometry for _, geometry in intersections])
        results[cell['id']] = {
            'buildingFeatureCount': len(intersections), 'unionAreaM2': union.area,
            'coveredFraction': union.area/cell['boundary'].area,
            'buildingIds': [snapshot['buildings'][i]['id'] for i, _ in intersections]}
    return results


def public_summary(report):
    cells = []
    for cell in report['cells']:
        methods = {}
        for method, values in cell['methods'].items():
            classes = []
            for code, areas in values['classes'].items():
                rows = [r for r in values['intersections'] if r['classCode'] == code]
                classes.append({'code': code, 'names': sorted({r['className'] for r in rows}),
                                'sourceImageDates': sorted({r['imageDate'] for r in rows if r['imageDate']}),
                                **areas})
            methods[method] = {k: v for k, v in values.items() if k not in ('intersections', 'classes')}
            methods[method]['classes'] = classes
        cells.append({k: cell[k] for k in ('id', 'kind', 'modelAreaM2', 'nativeAreaM2',
                     'nativeMinusModelAreaM2', 'outsideStudyAreaM2', 'numericAreaToleranceM2',
                     'methodComparison')} | {'methods': methods,
                     'buildingComparison': {k: v for k, v in report['buildingComparison'][cell['id']].items()
                                            if k != 'buildingIds'}})
    return {'schemaVersion': 1, 'status': report['status'], 'modelEligible': False,
            'calibrationEligible': False, 'inputHashes': report['inputHashes'],
            'reportSha256': hashlib.sha256(report_bytes(report)).hexdigest(),
            'sourceArchiveSha256': report['source']['sha256'], 'codeHashes': report['codeHashes'],
            'versions': report['versions'], 'sourceFeatureCount': report['sourceFeatureCount'],
            'originalInvalidCount': report['originalInvalidCount'], 'cells': cells,
            'placementOverlaps': report['placementOverlaps'],
            'placementAreaSumM2': report['placementAreaSumM2'],
            'placementAreaUnionM2': report['placementAreaUnionM2'],
            'limitations': ['기존 가정 구역과 서로 다른 제작 시점의 공개자료 대조',
                           '토지피복 분류는 실측 불투수율·침투율·시공 적합성이 아님',
                           '위상 보정 두 방식의 일치는 원본 경계의 현장 정확성 보증이 아님',
                           'IMG_DATE 원문 보존; 날짜 필드의 연말 표기를 정확 촬영일로 단정하지 않음',
                           '수치지도 건물 도형 중첩은 해당 연도 지붕·높이·구조 하중 검증이 아님',
                           '모델 및 기존 순위 변경 없음']}


def report_bytes(report):
    return (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def load_inputs():
    paths = {key: audit.ROOT/name for key, name in {
        'catalog': 'data/models/catalog.json', 'model': 'data/models/seongsu-lab.json',
        'map': 'frontend/public/data/seongsu.json', 'osm': 'data/raw/seongsu.osm',
        'mapManifest': 'data/manifests/public-data-audit.json',
        'mapTransform': 'scripts/prepare_public_data.py',
        'cellGenerator': 'scripts/prepare_lab_model.py',
        'engineGenerator': 'simulation/waterleague_sim/engine/swmm.py',
        'buildingSnapshot': 'backend/src/main/resources/spatial/seongsu-buildings.json',
        'buildingChecksum': 'backend/src/main/resources/spatial/seongsu-buildings.sha256'}.items()}
    hashes = {key: audit.digest(path) for key, path in paths.items()}
    values = {key: json.loads(paths[key].read_text()) for key in ('catalog', 'model', 'map', 'mapManifest')}
    manifest = values['mapManifest']['map']
    registered = [m for m in values['catalog']['models'] if m['file'] == 'seongsu-lab.json']
    if (len(registered) != 1 or registered[0]['sha256'] != hashes['model']
            or registered[0]['id'] != values['model']['id']
            or manifest['derivedHash'] != hashes['map'] or manifest['sourceHash'] != hashes['osm']
            or manifest['transformSha256'] != hashes['mapTransform']
            or values['model']['generatorSha256'] != hashes['engineGenerator']
            or paths['buildingChecksum'].read_text().strip() != hashes['buildingSnapshot']
            or values['map']['sourceHash'] != hashes['osm'] or values['map']['bounds'] != list(audit.BOUNDS)):
        raise audit.SpatialDataError('등록 지도·원본·모델 해시 연결 오류')
    return values['model'], values['map'], hashes, paths


def write_private(output, report):
    root = audit.ROOT/'data/private'
    target = Path(os.path.abspath(output))
    if not target.is_relative_to(root) or target == root:
        raise audit.SpatialDataError('상세 보고서는 data/private 내부 경로 필요')
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise audit.SpatialDataError('상세 보고서 링크 경로 거부')
    payload = report_bytes(report)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=audit.ROOT/'data/private/seongsu-official-20261017/landcover-2024.zip')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publish-summary', action='store_true')
    args = parser.parse_args()
    model, snapshot, hashes, paths = load_inputs()
    with tempfile.TemporaryDirectory(prefix='waterleague-cell-cover-') as directory:
        work = Path(directory)
        archive = audit.extract_checked(args.source, work/'source', audit.EXPECTED['landcover-2024'])
        study, crs = audit.study_boundary((work/'source/37705083.prj').read_text())
        transformer = pyproj.Transformer.from_pipeline(crs['pipeline'])
        cells = cell_boundaries(model, snapshot, transformer)
        building_comparison = compare_buildings(cells, json.loads(paths['buildingSnapshot'].read_text()), transformer)
        native = work/'native.json'
        audit.command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', native, work/'source/37705083.shp')
        if native.stat().st_size > 80*1024**2:
            raise audit.SpatialDataError('피복 변환 크기 초과')
        report = diagnose(json.loads(native.read_text())['features'], cells, study)
    if (any(audit.digest(path) != hashes[key] for key, path in paths.items())
            or audit.digest(args.source) != archive['sha256']):
        raise audit.SpatialDataError('검사 중 지도·모델 변경')
    report.update(schemaVersion=1, source=archive, inputHashes=hashes, crs=crs,
                  buildingComparison=building_comparison,
                  codeHashes={Path(p).name: audit.digest(Path(p)) for p in
                              (__file__, audit.__file__, topology.__file__)},
                  versions={'gdal': audit.command('gdalinfo', '--version').strip(),
                            'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                            'shapely': shapely.__version__, 'geos': shapely.geos_version_string})
    write_private(args.output, report)
    if args.publish_summary:
        destination = audit.ROOT/'data/manifests/seongsu-cell-landcover-audit.json'
        payload = report_bytes(public_summary(report))
        if destination.is_symlink() or destination.exists() and destination.read_bytes() != payload:
            raise audit.SpatialDataError('기존 공개 요약 덮어쓰기 금지; 새 버전 검토 필요')
        if not destination.exists():
            with destination.open('xb') as stream:
                stream.write(payload)
    print(json.dumps({'report': str(args.output), 'cells': len(cells),
                      'status': report['status'], 'modelEligible': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
