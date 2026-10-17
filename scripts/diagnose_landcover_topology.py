"""원본 토지피복의 두 위상 보정 후보 비교. 모델 채택·좌표 공개 없음."""
import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

import audit_spatial_sources as audit

METHODS = ('linework', 'structure')


def json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def geometry_hash(geometry):
    return hashlib.sha256(shapely.to_wkb(geometry, byte_order=1, output_dimension=2)).hexdigest()


def components(geometry):
    if hasattr(geometry, 'geoms'):
        return [part for child in geometry.geoms for part in components(child)]
    return [] if geometry.is_empty else [geometry]


def polygonal(geometry):
    return unary_union([g for g in components(geometry) if g.geom_type == 'Polygon'])


def describe(geometry):
    parts = components(geometry)
    residuals = [g for g in parts if g.geom_type != 'Polygon']
    return {'wkbSha256': geometry_hash(geometry), 'type': geometry.geom_type,
            'valid': bool(geometry.is_valid), 'empty': bool(geometry.is_empty),
            'areaM2': geometry.area, 'coordinateCount': int(shapely.get_num_coordinates(geometry)),
            'componentCounts': dict(sorted(Counter(g.geom_type for g in parts).items())),
            'nonAreaComponentCounts': dict(sorted(Counter(g.geom_type for g in residuals).items())),
            'nonAreaLengthM': math.fsum(g.length for g in residuals)}


def diagnose(features, boundary):
    if not boundary.is_valid or boundary.is_empty or boundary.area <= 0:
        raise audit.SpatialDataError('유효한 대상 면적 경계 필요')
    if len(features) > 100_000:
        raise audit.SpatialDataError('피복 도형 수 초과')
    before = json_hash(features)
    geometries = [shape(f['geometry']) for f in features]
    if any(g.geom_type not in ('Polygon', 'MultiPolygon') or g.has_z
           or not all(math.isfinite(v) for point in shapely.get_coordinates(g) for v in point)
           for g in geometries):
        raise audit.SpatialDataError('유한한 2차원 피복 폴리곤 필요')
    invalid_indexes = [i for i, g in enumerate(geometries) if not g.is_valid or g.is_empty]
    report = {'status': 'DIAGNOSTIC_ONLY', 'modelEligible': False, 'calibrationEligible': False,
              'featuresSha256': before, 'methods': {}, 'originalInvalidFeatures': [
                  {'featureIndex': i, 'propertiesSha256': json_hash(features[i]['properties']),
                   'classCode': features[i]['properties'].get('L3_CODE'),
                   'reason': shapely.is_valid_reason(geometries[i]), **describe(geometries[i])}
                  for i in invalid_indexes], 'originalAudit': audit.analyze_landcover(features, boundary)}
    candidates, clipped_by_method = {}, {}
    for method in METHODS:
        replacements, candidate_features, by_class, details = {}, [], defaultdict(list), []
        for i, (feature, original) in enumerate(zip(features, geometries)):
            candidate = original
            if i in invalid_indexes:
                # 선·점으로 퇴화한 성분을 진단에 남기고 면적 집계에서만 분리.
                fixed = shapely.make_valid(original, method=method, keep_collapsed=True)
                candidate = polygonal(fixed)
                if not fixed.is_valid or not candidate.is_valid:
                    raise audit.SpatialDataError('보정 후보 유효성 실패')
                replacements[i] = candidate
                details.append({'featureIndex': i, 'fullCandidate': describe(fixed),
                                'areaCandidate': describe(candidate),
                                'studyAreaM2': candidate.intersection(boundary).area})
                candidate_features.append({**feature, 'geometry': mapping(candidate)})
            else:
                candidate_features.append(feature)
            clip = candidate.intersection(boundary)
            if clip.area > 0:
                by_class[feature['properties']['L3_CODE']].append(clip)
        clipped = {code: unary_union(clips) for code, clips in sorted(by_class.items())}
        candidate_audit = audit.analyze_landcover(candidate_features, boundary)
        candidate_audit['study']['validGeometriesOnly'] = False
        candidate_audit['study']['geometryBasis'] = 'ORIGINAL_VALID_AND_REPAIRED_CANDIDATES'
        report['methods'][method] = {
            'keepCollapsed': True, 'changedFeatures': details,
            'unchangedOriginalValidFeatureCount': len(features)-len(invalid_indexes),
            'audit': candidate_audit,
            'classUnionAreasM2': {code: geometry.area for code, geometry in clipped.items()}}
        candidates[method], clipped_by_method[method] = replacements, clipped
    differences = []
    for i in invalid_indexes:
        left, right = candidates['linework'][i], candidates['structure'][i]
        differences.append({'featureIndex': i, 'sameAreaGeometry': bool(left.equals(right)),
            'wholeFeatureSymmetricDifferenceM2': left.symmetric_difference(right).area,
            'studySymmetricDifferenceM2': left.intersection(boundary).symmetric_difference(
                right.intersection(boundary)).area})
    left, right = clipped_by_method['linework'], clipped_by_method['structure']
    empty = GeometryCollection()
    report['methodComparison'] = {'features': differences,
        'classStudySymmetricDifferenceM2': {code: left.get(code, empty).symmetric_difference(
            right.get(code, empty)).area for code in sorted(left.keys() | right.keys())},
        'studyUnionSymmetricDifferenceM2': unary_union(list(left.values())).symmetric_difference(
            unary_union(list(right.values()))).area,
        'meaning': '방법 간 도형 일치도 원본 경계·분류·시점의 현장 정확성 보증이 아님'}
    if before != json_hash(features):
        raise audit.SpatialDataError('진단 중 원본 변형 감지')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path,
                        default=audit.ROOT/'data/private/seongsu-official-20261017/landcover-2024.zip')
    parser.add_argument('--output', type=Path,
                        default=audit.ROOT/'data/private/seongsu-official-20261017/topology-diagnostic.json')
    args = parser.parse_args()
    if args.output.exists():
        raise audit.SpatialDataError('기존 진단 파일 덮어쓰기 금지; 새 출력 경로 지정')
    with tempfile.TemporaryDirectory(prefix='waterleague-topology-') as directory:
        work = Path(directory)
        archive = audit.extract_checked(args.source, work/'source', audit.EXPECTED['landcover-2024'])
        boundary, crs = audit.study_boundary((work/'source/37705083.prj').read_text())
        native = work/'native.json'
        audit.command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949',
                      native, work/'source/37705083.shp')
        if native.stat().st_size > 80 * 1024**2:
            raise audit.SpatialDataError('피복 변환 출력 크기 초과')
        report = diagnose(json.loads(native.read_text())['features'], boundary)
    report.update(schemaVersion=1, source=archive, crs=crs, boundsWgs84=audit.BOUNDS,
                  modelSha256=audit.digest(audit.ROOT/'data/models/seongsu-lab.json'),
                  codeSha256=audit.digest(Path(__file__)),
                  auditCodeSha256=audit.digest(Path(audit.__file__)),
                  versions={'gdal': audit.command('gdalinfo', '--version').strip(),
                            'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                            'shapely': shapely.__version__, 'geos': shapely.geos_version_string})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({'report': str(args.output), 'status': report['status'],
                      'invalidFeatures': len(report['originalInvalidFeatures']),
                      'modelEligible': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
