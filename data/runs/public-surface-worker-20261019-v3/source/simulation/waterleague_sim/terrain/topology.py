"""두 복구 방식의 면적이 일치하는 명시적 파생 도형. 원본 유지."""
from copy import deepcopy
import hashlib

from pyproj import CRS
import shapely
from shapely.geometry import mapping, shape

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.coverage import polygon
from waterleague_sim.terrain.grid import digest


def components(geometry):
    if geometry.is_empty:
        return []
    if hasattr(geometry, 'geoms'):
        return [part for child in geometry.geoms for part in components(child)]
    return [geometry]


def geometry_hash(geometry):
    return hashlib.sha256(shapely.to_wkb(geometry, byte_order=1, output_dimension=2)).hexdigest()


def derive_consensus(records, source_wkt):
    crs = CRS.from_wkt(source_wkt)
    require(crs.is_projected and all(a.unit_conversion_factor == 1 for a in crs.axis_info[:2]),
            'TOPOLOGY_METRIC_SOURCE_REQUIRED')
    before = digest(records)
    derived, changes = deepcopy(records), []
    for index, row in enumerate(records):
        original = polygon(shape(row['geometry']))
        if original.is_valid:
            continue
        candidates = {method: shapely.make_valid(original, method=method, keep_collapsed=True)
                      for method in ('linework', 'structure')}
        evidence = {'id': row['id'], 'sourceGeometrySha256': geometry_hash(original),
            'sourceInvalidReason': shapely.is_valid_reason(original), 'methods': {}}
        acceptable = True
        for method, candidate in candidates.items():
            nonarea = [p for p in components(candidate) if p.geom_type != 'Polygon']
            evidence['methods'][method] = {'geometrySha256': geometry_hash(candidate),
                'type': candidate.geom_type, 'valid': bool(candidate.is_valid), 'empty': bool(candidate.is_empty),
                'areaM2': candidate.area, 'nonAreaComponents': len(nonarea),
                'nonAreaLengthM': sum(p.length for p in nonarea)}
            acceptable &= candidate.is_valid and not candidate.is_empty and not nonarea
            acceptable &= candidate.geom_type in ('Polygon', 'MultiPolygon')
        left, right = candidates.values()
        same = bool(left.equals(right))
        evidence.update(sameAreaGeometry=same,
                        symmetricDifferenceM2=left.symmetric_difference(right).area,
                        adopted=bool(acceptable and same))
        if evidence['adopted']:
            # 정점 순서만 정규화하며 스냅·buffer·원본 속성 변경은 하지 않는다.
            derived[index]['geometry'] = mapping(shapely.normalize(left))
            derived[index]['properties']['geometryDerivation'] = deepcopy(evidence)
        changes.append(evidence)
    require(digest(records) == before, 'TOPOLOGY_SOURCE_MUTATED')
    return derived, {'policy': 'EXPLICIT_TWO_METHOD_AREA_CONSENSUS_v1',
        'classification': 'DERIVED_GEOMETRY_NOT_FIELD_VERIFICATION', 'rankingEligible': False,
        'sourceRecordsSha256': before, 'derivedRecordsSha256': digest(derived),
        'changedFeatures': changes, 'adoptedCount': sum(c['adopted'] for c in changes),
        'unresolvedCount': sum(not c['adopted'] for c in changes),
        'shapelyVersion': shapely.__version__, 'geosVersion': shapely.geos_version_string,
        'limitations': ['두 방법의 일치는 원래 경계·분류의 현장 정확성 증명이 아님',
            '방법 불일치·선/점 퇴화는 원본 오류 상태 유지', '기존 모델·원본·기록의 소급 변경 없음']}
