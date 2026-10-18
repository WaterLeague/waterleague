"""공개 도형 내부의 고정 폭 직선 설계와 보수적인 길이 한도."""
try:
    from .straight_footprint import contained_rectangle
except ImportError:
    from straight_footprint import contained_rectangle


def contained_design(cell):
    physical = cell.get('physicalInputs', {})
    if (cell['kind'] != 'GROUND'
            or physical.get('soilStatus') != 'TEXTURE_CLASS_LITERATURE_ESTIMATE'
            or physical.get('slopeMethod') != 'NGII_2025_90M_HORN_TERRAIN_PROXY'
            or not .5 <= physical.get('slopePercent', -1) <= 3):
        return None
    return contained_rectangle(cell, 2, 'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY')
