"""지붕 유출을 강우 없는 별도 RB 용기에 전달하는 탐색 설계."""
import math
from ..spatial.cistern_game import rules, TYPE
from .swmm import SimulationQualityError


def apply(source, model, placement):
    cell = model['cells'][0]
    area = placement['areaM2']
    if (cell['kind'] != 'ROOF' or TYPE not in cell['allowedTypes']
            or placement['cellId'] != cell['id'] or type(area) not in (int, float)
            or not math.isfinite(area) or not 0 < area <= cell['maxAreaM2']
            or model.get('facilityDesignSet') != rules()['facilityDesignSet']):
        raise SimulationQualityError('CISTERN_GAME_PLACEMENT_INVALID')
    rule = rules()
    volume = area * rule['capacityPerRoofAreaM']
    tank_area = volume / (rule['storageDepthMm'] / 1000)
    sections, current = {}, None
    for line in source.splitlines():
        if line.startswith('['):
            current = line[1:-1]
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line)
    catchment = sections['SUBCATCHMENTS'][0].split()
    subarea = sections['SUBAREAS'][0].split()
    infiltration = sections['INFILTRATION'][0].split()
    total = cell['areaM2']
    collector = catchment.copy()
    collector[2:4] = ['WL_TANK', format(area / 10000, '.15g')]
    # 분할 전후 면적당 유출 폭을 같게 하여 집수 외 지붕의 조건을 보존한다.
    collector[5] = format(float(catchment[5]) * area / total, '.15g')
    sections['SUBCATCHMENTS'] = [' '.join(collector)]
    sections['SUBAREAS'] = [' '.join(subarea)]
    sections['INFILTRATION'] = [' '.join(infiltration)]
    if total - area > 1e-8:
        rest = catchment.copy()
        rest[0], rest[3] = 'WL_ROOF_REST', format((total - area) / 10000, '.15g')
        rest[5] = format(float(catchment[5]) * (total - area) / total, '.15g')
        sections['SUBCATCHMENTS'].append(' '.join(rest))
        sections['SUBAREAS'].append(' '.join(['WL_ROOF_REST', *subarea[1:]]))
        sections['INFILTRATION'].append(' '.join(['WL_ROOF_REST', *infiltration[1:]]))
    # 용기는 집수면 밖의 계산 요소다. 동일 지붕 강우를 탱크에 다시 입력하지 않는다.
    sections['SUBCATCHMENTS'].append(
        f'WL_TANK WL_NO_RAIN OUT {tank_area / 10000:.15g} 100 1 1 0')
    sections['SUBAREAS'].append('WL_TANK 0.012 0.15 0 0 100 OUTLET 100')
    sections['INFILTRATION'].append('WL_TANK 88.9 3.302 0.231')
    sections['LID_CONTROLS'] = [
        'WL_RB RB',
        f'WL_RB STORAGE {rule["storageDepthMm"]} 1 0 0 YES',
        f'WL_RB DRAIN {rule["drainCoefficient"]:.15g} {rule["drainExponent"]} '
        f'{rule["drainOffsetMm"]} {rule["drainDelayHours"]}']
    sections['LID_USAGE'] = [f'WL_TANK WL_RB 1 {tank_area:.15g} 0 0 100 0 * OUT 0']
    return '\n\n'.join('[' + key + ']\n' + '\n'.join(rows) for key, rows in sections.items()) + '\n'
