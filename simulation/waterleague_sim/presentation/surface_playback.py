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
    convert, operation = projection(terrain['coordinateWkt'], CRS('EPSG:5186').to_wkt(),
                                   city.get('originProjected'), [126.7, 37.3, 127.3, 37.8])
    points = reader.mesh['vertices'][:, :2] + origin
    x, y = convert(points[:, 0], points[:, 1])
    xy = np.column_stack((x, y))
    require(np.all(np.isfinite(xy)) and np.max(np.abs(xy)) <= 60000,
            'SURFACE_PLAYBACK_OUTSIDE_MAP')
    directory = Path(directory)
    require(not directory.exists(), 'SURFACE_PLAYBACK_OUTPUT_EXISTS')
    directory.mkdir(parents=True)

    def write(name, raw):
        with (directory/name).open('xb') as out:
            out.write(raw)
        return {'file': name, 'sha256': sha(raw), 'bytes': len(raw)}

    mesh = write('mesh.json', encode({'vertices': xy.tolist(),
        'triangles': reader.mesh['triangles'].tolist(), 'areasM2': reader.mesh['areas'].tolist()}))
    frames = []
    for index, item in enumerate(source['frames']):
        # 모든 원 프레임의 수지·해시를 검사하고 동일 이진값만 전달한다.
        reader.frame(index)
        raw = (reader.root/item['file']).read_bytes()
        require(sha(raw) == item['sha256'], 'SURFACE_FRAME_HASH_MISMATCH')
        frames.append(write(item['file'], raw) | {'index': index, 'timeSeconds': item['timeSeconds'],
            'storageM3': item['storageM3'], 'sourceSha256': item['sha256']})
    catalog = {'schemaVersion': 1, 'type': 'SURFACE_PLAYBACK', 'rankingEligible': False,
        'classification': source['classification'], 'startUtc': start,
        'coordinateSystem': 'EPSG:5186', 'originProjected': city['originProjected'],
        'sourceCoordinateSystem': source['coordinateSystem'], 'verticalDatum': source['verticalDatum'],
        'verticalPlacement': 'TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION',
        'triangleCount': reader.count, 'mesh': mesh, 'frames': frames,
        'surfaceResultSha256': result_sha256,
        'sourceCatalogSha256': reader.result['surfaceFrames']['sha256'],
        'projection': operation, 'velocityDepthThresholdM': source['velocityDepthThresholdM'],
        'sourceCodeSha256': sha(Path(__file__).read_bytes()),
        'limitations': source['limitations'] + terrain.get('limitations', []) + [
            '색상은 계산 격자 중심 수심·속력이며 지도 지표면에 표시; 실제 수면 표고 아님',
            '속력은 원 좌표 운동량/수심의 크기; 지도 투영 방향 벡터 아님']}
    saved = write('catalog.json', encode(catalog))
    return {'schemaVersion': 1, 'catalogSha256': saved['sha256'],
            'surfaceResultSha256': result_sha256, 'rankingEligible': False}
