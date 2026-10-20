"""원본 폴리곤과 지표 삼각형의 면적 교차. 결측·중복·오류 도형 보존."""
from copy import deepcopy
import hashlib
import math

import numpy as np
import pyproj
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.transformer import TransformerGroup
import shapely
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.grid import digest, finite

EMPTY = Polygon()


def polygon(geometry):
    coordinates = shapely.get_coordinates(geometry)
    require(geometry.geom_type in ('Polygon', 'MultiPolygon') and not geometry.is_empty
            and not geometry.has_z and not geometry.has_m
            and len(coordinates) >= 4 and np.all(np.isfinite(coordinates)),
            'COVERAGE_POLYGON_INVALID')
    return geometry


def projection(source_crs, target_wkt, origin, bounds):
    require(isinstance(origin, list) and len(origin) == 2 and all(map(finite, origin)),
            'COVERAGE_ORIGIN_INVALID')
    target = CRS.from_wkt(target_wkt)
    require(target.is_projected and all(a.unit_conversion_factor == 1 for a in target.axis_info[:2]),
            'COVERAGE_METRIC_CRS_REQUIRED')
    pyproj.network.set_network_enabled(False)
    group = TransformerGroup(source_crs, target, always_xy=True, allow_ballpark=False,
                             area_of_interest=AreaOfInterest(*bounds))
    require(group.best_available and group.transformers, 'COVERAGE_TRANSFORM_UNAVAILABLE')
    operation = group.transformers[0]
    require(not any(o.has_ballpark_transformation for o in operation.operations),
            'COVERAGE_BALLPARK_TRANSFORM_FORBIDDEN')

    def local(x, y):
        a, b = operation.transform(x, y, errcheck=True)
        return np.asarray(a) - origin[0], np.asarray(b) - origin[1]

    return local, {'sourceWkt': CRS(source_crs).to_wkt(), 'targetWkt': target_wkt,
        'originProjected': list(origin), 'description': operation.description,
        'pipeline': operation.definition, 'statedAccuracyM': operation.accuracy,
        'accuracyKnown': operation.accuracy >= 0, 'coordinateEpoch': None,
        'bestOperationAvailable': group.best_available, 'allowBallpark': False,
        'edgePolicy': 'TRANSFORM_ORIGINAL_VERTICES_LINEAR_EDGES',
        'runtime': {'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                    'shapely': shapely.__version__, 'geos': shapely.geos_version_string}}


class PolygonLayer:
    def __init__(self, records, convert, provenance):
        require(isinstance(records, list) and len(records) <= 100_000, 'COVERAGE_RECORDS_INVALID')
        self.records, self.geometries, self.invalid, self.envelopes = [], [], [], []
        ids = set()
        for row in records:
            require(isinstance(row, dict) and isinstance(row.get('id'), str) and row['id']
                    and row['id'] not in ids and isinstance(row.get('properties'), dict),
                    'COVERAGE_RECORD_INVALID')
            ids.add(row['id'])
            original = polygon(shape(row['geometry']))
            projected = polygon(shapely.transform(original, convert, interleaved=False))
            record = {'id': row['id'], 'properties': deepcopy(row['properties']),
                'sourceGeometrySha256': hashlib.sha256(original.wkb).hexdigest(),
                'projectedGeometrySha256': hashlib.sha256(projected.wkb).hexdigest()}
            if not original.is_valid or not projected.is_valid:
                self.invalid.append(record | {'sourceReason': shapely.is_valid_reason(original),
                    'projectedReason': shapely.is_valid_reason(projected)})
                self.envelopes.append(projected.envelope)
                continue
            require(projected.area > 0, 'COVERAGE_POLYGON_INVALID')
            self.records.append(record)
            self.geometries.append(projected)
        self.tree, self.invalid_tree = shapely.STRtree(self.geometries), shapely.STRtree(self.envelopes)
        self.provenance = deepcopy(provenance) | {'recordsSha256': digest(records),
            'validFeatures': len(self.records), 'invalidFeatures': len(self.invalid)}

    def measure(self, boundary):
        require(boundary.is_valid and boundary.area > 0, 'COVERAGE_BOUNDARY_INVALID')
        clips, merged, overlap = [], EMPTY, EMPTY
        for index in sorted(map(int, self.tree.query(boundary, predicate='intersects'))):
            clip = boundary.intersection(self.geometries[index])
            if clip.area <= 0:
                continue
            # 동일 분류 중복도 우선순위를 정하지 않고 별도 면적으로 남긴다.
            overlap = overlap.union(merged.intersection(clip))
            merged = merged.union(clip)
            clips.append((index, clip))
        invalid_ids, invalid_clips = [], []
        for index in sorted(map(int, self.invalid_tree.query(boundary, predicate='intersects'))):
            clip = boundary.intersection(self.envelopes[index])
            if clip.area > 0:
                invalid_ids.append(index)
                invalid_clips.append(clip)
        affected = unary_union(invalid_clips)
        ambiguous = overlap.union(affected)
        exclusive = [(i, clip.difference(ambiguous)) for i, clip in clips]
        exclusive = [(i, clip) for i, clip in exclusive if clip.area > 0]
        assigned = unary_union([clip for _, clip in exclusive])
        return {'areaM2': boundary.area, 'coveredValidAreaM2': merged.area,
            'gapAreaM2': boundary.difference(merged).area, 'overlapAreaM2': overlap.area,
            'invalidEnvelopeAffectedAreaM2': affected.area,
            'exclusiveAreaM2': assigned.area, 'unresolvedAreaM2': boundary.difference(assigned).area,
            'invalidFeatureIds': [self.invalid[i]['id'] for i in invalid_ids],
            'intersections': [{'id': self.records[i]['id'], 'areaM2': clip.area} for i, clip in clips],
            'exclusiveParts': [{'id': self.records[i]['id'], 'areaM2': clip.area} for i, clip in exclusive]}, exclusive


def mesh_polygons(model):
    vertices, triangles = model.get('verticesM'), model.get('triangles')
    require(isinstance(vertices, list) and all(isinstance(p, list) and len(p) == 2
            and all(map(finite, p)) for p in vertices) and isinstance(triangles, list)
            and 0 < len(triangles) <= 200_000, 'COVERAGE_MESH_INVALID')
    result = []
    for indices in triangles:
        require(isinstance(indices, list) and len(indices) == 3 and len(set(indices)) == 3
                and all(type(i) is int and 0 <= i < len(vertices) for i in indices),
                'COVERAGE_MESH_INVALID')
        p = Polygon([vertices[i] for i in indices])
        require(p.is_valid and p.area > 0, 'COVERAGE_MESH_INVALID')
        result.append(p)
    require(abs(math.fsum(p.area for p in result) - unary_union(result).area) <= 1e-8,
            'COVERAGE_MESH_OVERLAP')
    return result


def assign(model, soil, landcover):
    cells = []
    for index, boundary in enumerate(mesh_polygons(model)):
        soil_report, soil_parts = soil.measure(boundary)
        cover_report, cover_parts = landcover.measure(boundary)
        joint, joint_geometries = [], []
        for si, sp in soil_parts:
            for ci, cp in cover_parts:
                clip = sp.intersection(cp)
                if clip.area > 0:
                    joint.append({'soilId': soil.records[si]['id'], 'landcoverId': landcover.records[ci]['id'],
                                  'areaM2': clip.area, 'areaFraction': clip.area / boundary.area})
                    joint_geometries.append(clip)
        covered = unary_union(joint_geometries)
        cells.append({'triangle': index, 'areaM2': boundary.area, 'soil': soil_report,
            'landcover': cover_report, 'jointParts': joint, 'jointAreaM2': covered.area,
            'jointUnresolvedAreaM2': boundary.difference(covered).area})
    total = math.fsum(c['areaM2'] for c in cells)
    metrics = ('coveredValidAreaM2', 'gapAreaM2', 'overlapAreaM2',
               'invalidEnvelopeAffectedAreaM2', 'exclusiveAreaM2', 'unresolvedAreaM2')
    return {'schemaVersion': 1, 'classification': 'PUBLIC_SPATIAL_ASSIGNMENT_NOT_HYDRAULIC_PARAMETERS',
        'rankingEligible': False, 'modelSha256': digest(model),
        'soilSource': soil.provenance, 'landcoverSource': landcover.provenance,
        'soilRecords': soil.records, 'landcoverRecords': landcover.records,
        'invalidSoilRecords': soil.invalid, 'invalidLandcoverRecords': landcover.invalid,
        'triangles': cells, 'totals': {'areaM2': total, 'triangles': len(cells),
            'soil': {m: math.fsum(c['soil'][m] for c in cells) for m in metrics},
            'landcover': {m: math.fsum(c['landcover'][m] for c in cells) for m in metrics},
            'jointAreaM2': math.fsum(c['jointAreaM2'] for c in cells),
            'jointUnresolvedAreaM2': math.fsum(c['jointUnresolvedAreaM2'] for c in cells)},
        'physicalParameters': {'status': 'UNRESOLVED', 'imperviousFraction': None,
            'roughness': None, 'initialSoilMoisture': None,
            'reason': '공개 피복·심토 토성 분류만으로 실제 포장률·표면 다짐·초기 수분 확정 불가'},
        'limitations': ['오류 도형의 envelope는 영향 가능 범위이며 실제 중첩/누락 면적이 아님',
            '틈·중복·오류 영향 영역은 자동 복구·최근접 배정·정규화하지 않음',
            '원본 꼭짓점 좌표 변환 후 직선 연결; 변환 정확도와 원본 위치 정확도 구분',
            '현재 공개 토양·2024판 피복·2025판 DEM의 결합이며 2010/2011/2022 당시 복원 아님']}


def infiltration_from_assignment(model, assignment, soil_parameters, cover_parameters, *, initialization):
    """전체 면적의 명시적 물리 근거가 있는 배정만 침투 입력으로 변환."""
    from .rainfall_coverage import surface_fractions
    require(all(value in (0, 1) for value in surface_fractions(model)),
            'COVERAGE_RAIN_PARTITION_GEOMETRY_REQUIRED')
    require(assignment.get('schemaVersion') == 1 and assignment.get('triangles')
            and assignment.get('modelSha256') == digest(model),
            'COVERAGE_ASSIGNMENT_INVALID')
    require(isinstance(initialization, dict) and initialization.get('evidence'),
            'COVERAGE_INITIALIZATION_REQUIRED')
    owners = model['rainfallOwner']
    require(len(assignment['triangles']) == len(owners), 'COVERAGE_ASSIGNMENT_INVALID')
    regions, sealed, checksum = [], [], digest(assignment)
    for index, cell in enumerate(assignment['triangles']):
        require(cell['triangle'] == index, 'COVERAGE_ASSIGNMENT_INVALID')
        if owners[index] == 'NETWORK':
            continue
        require(cell['jointUnresolvedAreaM2'] / cell['areaM2'] <= 1e-12,
                'COVERAGE_SPATIAL_ASSIGNMENT_INCOMPLETE')
        for part in cell['jointParts']:
            soil = soil_parameters.get(part['soilId'])
            cover = cover_parameters.get(part['landcoverId'])
            require(isinstance(cover, dict) and cover.get('evidence')
                    and finite(cover.get('perviousFraction')) and 0 <= cover['perviousFraction'] <= 1,
                    'COVERAGE_SURFACE_MATERIAL_REQUIRED')
            wet, area = cover['perviousFraction'], part['areaFraction']
            evidence = {'assignmentSha256': checksum, 'soilId': part['soilId'],
                'landcoverId': part['landcoverId'], 'cover': deepcopy(cover)}
            if wet > 0:
                require(isinstance(soil, dict) and soil.get('evidence'), 'COVERAGE_SOIL_PARAMETERS_REQUIRED')
                regions.append({'triangles': [cell['triangle']], 'perviousFraction': area * wet,
                    'suctionMm': soil.get('suctionMm'), 'conductivityMmH': soil.get('conductivityMmH'),
                    'initialMoistureDeficit': initialization.get('initialMoistureDeficit'),
                    'evidence': evidence | {'soil': deepcopy(soil)}})
            if wet < 1:
                sealed.append({'triangles': [cell['triangle']], 'areaFraction': area * (1-wet),
                               'evidence': evidence})
    result = {'schemaVersion': 2, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'partitionPolicy': 'EXPLICIT_AREA_FRACTIONS', 'initialization': 'EPA_INITIAL_DEFICIT_SEED',
        'recoveryFactor': initialization.get('recoveryFactor'), 'evidence': deepcopy(initialization),
        'regions': regions, 'imperviousRegions': sealed}
    from waterleague_sim.engine.surface_infiltration import validate
    return validate(result, owners)
