"""공개 토성 지상 후보의 개방형 침투 트렌치 배치."""
try:
    from .straight_footprint import contained_rectangle
except ImportError:
    from straight_footprint import contained_rectangle

def contained_design(cell):
    physical = cell.get('physicalInputs', {})
    if (cell['kind'] != 'GROUND'
            or physical.get('soilStatus') != 'TEXTURE_CLASS_LITERATURE_ESTIMATE'
            or physical.get('conductivityMmH', 0) <= 0):
        return None
    return contained_rectangle(cell, 1, 'LEVEL_STORAGE_DESIGN_NOT_SURVEY')
