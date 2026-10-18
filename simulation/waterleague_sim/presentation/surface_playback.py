"""해시 검증한 지표 결과를 서울 공통 지도 좌표와 원 프레임으로 전달."""
from pathlib import Path
import math

import numpy as np
from pyproj import CRS

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_frame_reader import NativeFrameReader
from waterleague_sim.engine.surface_frames import encode, sha
from waterleague_sim.forcing.stage import utc
from waterleague_sim.terrain.coverage import projection
from waterleague_sim.presentation.surface_directions import direction_basis, METHOD


def export_playback(surface_directory, result_sha256, directory, city):
    reader = NativeFrameReader(surface_directory, result_sha256)
    source = reader.catalog
    terrain = source.get('terrainProvenance')
    require(isinstance(terrain, dict) and isinstance(terrain.get('coordinateWkt'), str)
            and source['coordinateSystem'].startswith('SOURCE_PROJECTED_LOCAL:'),
            'SURFACE_PLAYBACK_SOURCE_CRS_REQUIRED')
    origin = terrain.get('originProjected')
    require(isinstance(origin, list) and len(origin) == 2
            and all(type(v) in (int, float) and math.isfinite(v) for v in origin),
            'SURFACE_PLAYBACK_SOURCE_ORIGIN_REQUIRED')
    require(city.get('coordinateSystem') == 'EPSG:5186', 'SURFACE_PLAYBACK_MAP_CRS_INVALID')
    start = utc(source.get('startUtc')).isoformat()
    crs = CRS.from_wkt(terrain['coordinateWkt'])
    require(crs.is_projected and all(a.unit_conversion_factor == 1 for a in crs.axis_info[:2]),
            'SURFACE_PLAYBACK_SOURCE_METRIC_CRS_REQUIRED')
    convert, operation = projection(terrain['coordinateWkt'], CRS('EPSG:5186').to_wkt(),
                                   city.get('originProjected'), [126.7, 37.3, 127.3, 37.8])
    points = reader.mesh['vertices'][:, :2] + origin
    x, y = convert(points[:, 0], points[:, 1])
    xy = np.column_stack((x, y))
    require(np.all(np.isfinite(xy)) and np.max(np.abs(xy)) <= 60000,
            'SURFACE_PLAYBACK_OUTSIDE_MAP')
    centers = points[reader.mesh['triangles']].mean(axis=1)
    basis, direction = direction_basis(convert, centers)
    directory = Path(directory)
    require(not directory.exists(), 'SURFACE_PLAYBACK_OUTPUT_EXISTS')
    directory.mkdir(parents=True)

    def write(name, raw):
        with (directory/name).open('xb') as out:
            out.write(raw)
        return {'file': name, 'sha256': sha(raw), 'bytes': len(raw)}

    mesh = write('mesh.json', encode({'vertices': xy.tolist(),
        'triangles': reader.mesh['triangles'].tolist(), 'areasM2': reader.mesh['areas'].tolist(),
        'directionBasis': basis}))
    frames = []
    for index, item in enumerate(source['frames']):
        # 모든 원 프레임의 수지·해시를 검사하고 동일 이진값만 전달한다.
        reader.frame(index)
        raw = (reader.root/item['file']).read_bytes()
        require(sha(raw) == item['sha256'], 'SURFACE_FRAME_HASH_MISMATCH')
        frames.append(write(item['file'], raw) | {'index': index, 'timeSeconds': item['timeSeconds'],
            'storageM3': item['storageM3'], 'sourceSha256': item['sha256']})
    catalog = {'schemaVersion': 2, 'type': 'SURFACE_PLAYBACK', 'rankingEligible': False,
        'classification': source['classification'], 'startUtc': start,
        'coordinateSystem': 'EPSG:5186', 'originProjected': city['originProjected'],
        'sourceCoordinateSystem': source['coordinateSystem'], 'verticalDatum': source['verticalDatum'],
        'verticalPlacement': 'TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION',
        'triangleCount': reader.count, 'mesh': mesh, 'frames': frames,
        'surfaceResultSha256': result_sha256,
        'sourceCatalogSha256': reader.result['surfaceFrames']['sha256'],
        'projection': operation, 'velocityDepthThresholdM': source['velocityDepthThresholdM'],
        'flowDirectionMethod': METHOD, 'directionProjection': direction,
        'directionCodeSha256': sha((Path(__file__).parent/'surface_directions.py').read_bytes()),
        'sourceCodeSha256': sha(Path(__file__).read_bytes()),
        'limitations': source['limitations'] + terrain.get('limitations', []) + [
            '색상은 계산 격자 중심 수심·속력이며 지도 지표면에 표시; 실제 수면 표고 아님',
            '속력은 원 좌표 운동량/수심의 크기, 흐름 방향만 지도 투영의 국소 미분으로 변환',
            '화살표는 격자 중심 흐름의 표시용 선택이며 길이는 속력·이동 거리를 뜻하지 않음']}
    saved = write('catalog.json', encode(catalog))
    return {'schemaVersion': 1, 'catalogSha256': saved['sha256'],
            'surfaceResultSha256': result_sha256, 'rankingEligible': False}
