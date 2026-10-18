"""공개 블록 면적비를 원본 지표 격자에 면적 가중 배정."""
from collections import Counter
import math

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.seoul_biotope import FIELDS
from waterleague_sim.terrain.coverage import mesh_polygons
from waterleague_sim.terrain.grid import digest


def assign_composition(model, layer):
    cells, issues = [], Counter()
    for index, boundary in enumerate(mesh_polygons(model)):
        coverage, clips = layer.measure(boundary)
        parts, unresolved = [], []
        for ri, clip in clips:
            row = layer.records[ri]
            value = row['properties']['composition']
            if value['status'] != 'CONSISTENT_REPORTED_COMPOSITION':
                unresolved.append({'id': row['id'], 'areaM2': clip.area, 'issues': value['issues']})
                issues.update(value['issues'])
                continue
            parts.append({'id': row['id'], 'areaM2': clip.area,
                'componentAreasM2': {key: clip.area * fraction
                                     for key, fraction in value['componentFractions'].items()},
                'reportedImperviousAreaM2': clip.area * value['reportedImperviousFraction'],
                'warnings': value['warnings'], 'physicsRequirements': value['physicsRequirements']})
        known = math.fsum(p['areaM2'] for p in parts)
        component_areas = {key: math.fsum(p['componentAreasM2'][key] for p in parts) for key in FIELDS}
        residual = math.fsum(component_areas.values()) - known
        require(abs(residual) <= max(1e-8, known * 1e-9), 'COMPOSITION_AREA_BALANCE_INVALID')
        cells.append({'triangle': index, 'areaM2': boundary.area, 'coverage': coverage,
            'parts': parts, 'invalidAttributeParts': unresolved,
            'knownCompositionAreaM2': known, 'componentAreasM2': component_areas,
            'reportedImperviousAreaM2': math.fsum(p['reportedImperviousAreaM2'] for p in parts),
            'unresolvedAreaM2': coverage['unresolvedAreaM2'] + math.fsum(p['areaM2'] for p in unresolved),
            'componentAreaResidualM2': residual})
    total = math.fsum(c['areaM2'] for c in cells)
    known = math.fsum(c['knownCompositionAreaM2'] for c in cells)
    components = {key: math.fsum(c['componentAreasM2'][key] for c in cells) for key in FIELDS}
    return {'schemaVersion': 1, 'classification': 'PUBLIC_BLOCK_COMPOSITION_UNIFORM_WITHIN_BLOCK',
        'rankingEligible': False, 'modelSha256': digest(model), 'source': layer.provenance,
        'triangles': cells, 'totals': {'areaM2': total, 'knownCompositionAreaM2': known,
            'unresolvedAreaM2': math.fsum(c['unresolvedAreaM2'] for c in cells),
            'componentAreasM2': components,
            'reportedImperviousAreaM2': math.fsum(c['reportedImperviousAreaM2'] for c in cells),
            'knownAreaComponentFractions': {key: area / known if known else None for key, area in components.items()},
            'areaAccountingResidualM2': total - known - math.fsum(c['unresolvedAreaM2'] for c in cells)},
        'limitations': ['원본 블록 내부의 각 격자에 같은 면적비 배정; 실제 포장 위치를 측량한 분포 아님',
            '미해결 면적은 0% 또는 100% 불투수로 채우거나 알려진 면적에 재배분하지 않음',
            '투수포장과 녹지·나지 구분; 포장층 제원·토양·조도·초기 수분은 별도 입력 필요',
            '자료 판년도와 사건 당일 유효성 구분; 현장 침수 정확도·경쟁 등급 승격 없음']}
