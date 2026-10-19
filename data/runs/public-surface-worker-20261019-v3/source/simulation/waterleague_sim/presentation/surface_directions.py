"""원 운동량의 방향을 지도 투영으로 옮기는 표시 전용 국소 변환."""
import numpy as np

from waterleague_sim.engine.flood_errors import require

METHOD = 'SOURCE_MOMENTUM_LOCAL_PROJECTION_JACOBIAN_V1'


def direction_basis(convert, centers):
    points = np.asarray(centers, dtype=np.float64)
    require(points.ndim == 2 and points.shape[1] == 2 and np.all(np.isfinite(points)),
            'SURFACE_DIRECTION_CENTERS_INVALID')

    def differentiate(step):
        columns = []
        for axis in range(2):
            offset = np.zeros(2); offset[axis] = step
            high, low = points + offset, points - offset
            a = np.column_stack(convert(high[:, 0], high[:, 1]))
            b = np.column_stack(convert(low[:, 0], low[:, 1]))
            columns.append((a-b)/(2*step))
        return np.stack(columns, axis=2)

    full, half = differentiate(.5), differentiate(.25)
    require(np.all(np.isfinite(full)) and np.all(np.isfinite(half)), 'SURFACE_DIRECTION_NONFINITE')
    error = np.max(np.abs(full-half), axis=(1, 2)) / np.maximum(1., np.max(np.abs(half), axis=(1, 2)))
    require(np.all(error <= 1e-6) and np.all(np.abs(np.linalg.det(half)) > 1e-12)
            and np.max(np.abs(half)) <= 1000, 'SURFACE_DIRECTION_PROJECTION_UNSTABLE')
    return half.reshape((-1, 4)).tolist(), {'method': METHOD,
        'coordinateSystem': 'EPSG:5186', 'axisOrder': 'EASTING_NORTHING',
        'matrixOrder': ['dXdx', 'dXdy', 'dYdx', 'dYdy'], 'differenceStepM': .25,
        'comparisonStepM': .5, 'maximumRelativeDifference': float(np.max(error)),
        'relativeDifferenceLimit': 1e-6, 'sourceFramesUnchanged': True}


def flow_direction(basis, vx, vy, depth):
    if depth <= 1e-6 or (vx == 0 and vy == 0):
        return None
    a, b, c, d = basis
    x, y = a*vx+b*vy, c*vx+d*vy
    norm = float(np.hypot(x, y))
    require(np.isfinite(norm) and norm > 0, 'SURFACE_DIRECTION_VECTOR_INVALID')
    return [float(x/norm), float(y/norm)]
