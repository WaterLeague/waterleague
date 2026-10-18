"""해시로 고정한 계산 결과에서 요청 시각·영역의 중심값만 조회."""
from bisect import bisect_right
import json
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.surface_frames import FIELDS, VELOCITY_DEPTH_M, encode, sha
from waterleague_sim.forcing.stage import clamp_clock_roundoff


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'SURFACE_FRAME_DUPLICATE_FIELD')
            result[key] = value
        return result
    def invalid(_):
        raise FloodModelError('SURFACE_FRAME_JSON_INVALID')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, ValueError) as error:
        if isinstance(error, FloodModelError):
            raise
        raise FloodModelError('SURFACE_FRAME_JSON_INVALID') from None


def _read(path, expected, limit):
    require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected)
            and not any(p.is_symlink() for p in (path, *path.parents))
            and path.is_file() and path.stat().st_size <= limit, 'SURFACE_FRAME_FILE_INVALID')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    require(len(raw) <= limit and sha(raw) == expected, 'SURFACE_FRAME_HASH_MISMATCH')
    return raw


class NativeFrameReader:
    def __init__(self, directory, result_sha256):
        import numpy as np
        self.np = np
        self.directory = Path(directory).absolute()
        self.result = _json(_read(self.directory/'surface-result.json', result_sha256, 64*1024**2))
        require(isinstance(self.result, dict) and self.result.get('numericalStatus') == 'PASSED'
                and isinstance(self.result.get('numericalQuality', {}), dict)
                and self.result.get('numericalQuality', {}).get('status', 'PASSED') == 'PASSED'
                and isinstance(self.result.get('files'), dict),
                'SURFACE_FRAME_FAILED_RESULT')
        descriptor = self.result.get('surfaceFrames')
        require(isinstance(descriptor, dict) and descriptor.get('catalogFile') == 'native-frames/catalog.json'
                and descriptor.get('type') == 'NATIVE_CENTROID_FLOAT64', 'SURFACE_FRAME_CATALOG_REQUIRED')
        self.root = self.directory/'native-frames'
        require(self.result.get('files', {}).get(descriptor['catalogFile']) == descriptor.get('sha256'),
                'SURFACE_FRAME_RESULT_BINDING_INVALID')
        self.catalog = catalog = _json(_read(self.root/'catalog.json', descriptor['sha256'], 8*1024**2))
        require(isinstance(catalog, dict) and type(catalog.get('schemaVersion')) is int
                and catalog['schemaVersion'] == 1 and catalog.get('type') == 'NATIVE_CENTROID_FLOAT64'
                and catalog.get('numericalStatus') == 'PASSED' and catalog.get('rankingEligible') is False
                and catalog.get('frameFields') == FIELDS and catalog.get('frameDtype') == '<f8'
                and catalog.get('velocityDepthThresholdM') == VELOCITY_DEPTH_M,
                'SURFACE_FRAME_CATALOG_INVALID')
        self.count = catalog.get('triangleCount')
        vertices = catalog.get('vertexCount')
        require(type(self.count) is int and 1 <= self.count <= 200_000
                and type(vertices) is int and 3 <= vertices <= 500_000,
                'SURFACE_FRAME_MESH_LIMIT')
        input_hash = catalog.get('inputFileSha256')
        require(self.result['files'].get('surface-input.json') == input_hash, 'SURFACE_FRAME_RESULT_BINDING_INVALID')
        model = _json(_read(self.directory/'surface-input.json', input_hash, 64*1024**2))
        require(isinstance(model, dict) and sha(encode(model)) == catalog.get('modelSha256')
                and model.get('coordinateSystem') == catalog.get('coordinateSystem')
                and model.get('verticalDatum') == catalog.get('verticalDatum')
                and model.get('startUtc') == catalog.get('startUtc')
                and model.get('terrainProvenance') == catalog.get('terrainProvenance')
                and model.get('evidence') == catalog.get('classification'),
                'SURFACE_FRAME_MODEL_BINDING_INVALID')
        layout = {'vertices': ('<f8', [vertices, 3]), 'triangles': ('<u4', [self.count, 3]),
                  'centroids': ('<f8', [self.count, 3]), 'areas': ('<f8', [self.count])}
        require(isinstance(catalog.get('mesh'), dict) and set(catalog['mesh']) == set(layout),
                'SURFACE_FRAME_MESH_INVALID')
        self.mesh = {}
        for name, (dtype, shape) in layout.items():
            meta = catalog['mesh'][name]
            require(isinstance(meta, dict) and meta.get('file') == name+'.bin'
                    and meta.get('dtype') == dtype and meta.get('shape') == shape,
                    'SURFACE_FRAME_MESH_INVALID')
            size = math.prod(shape)*np.dtype(dtype).itemsize
            self.mesh[name] = np.frombuffer(self._binary(meta, size), dtype=dtype).reshape(shape)
        points, cells, centers, areas = (self.mesh[k] for k in ('vertices', 'triangles', 'centroids', 'areas'))
        require(all(np.all(np.isfinite(a)) for a in (points, centers, areas)) and np.all(areas > 0)
                and np.all(cells < vertices) and np.array_equal(cells, model['triangles'])
                and np.array_equal(points[:, :2], model['verticesM'])
                and np.array_equal(points[:, 2], model['elevationM']), 'SURFACE_FRAME_MESH_INVALID')
        self.xy_min = points[cells, :2].min(axis=1)
        self.xy_max = points[cells, :2].max(axis=1)
        rows = catalog.get('frames')
        require(isinstance(rows, list) and 1 <= len(rows) <= 10000
                and len(rows) == catalog.get('frameCount') == descriptor.get('frameCount')
                and descriptor.get('triangleCount') == self.count, 'SURFACE_FRAME_INDEX_INVALID')
        self.times = []
        for index, row in enumerate(rows):
            require(isinstance(row, dict) and row.get('index') == index
                    and row.get('file') == f'frame-{index:05d}.bin'
                    and type(row.get('timeSeconds')) in (int, float) and math.isfinite(row['timeSeconds'])
                    and (row['timeSeconds'] == 0 if not index else row['timeSeconds'] > self.times[-1])
                    and type(row.get('storageM3')) in (int, float) and math.isfinite(row['storageM3'])
                    and row.get('bytes') == self.count*3*8
                    and self.result['files'].get('native-frames/'+row['file']) == row.get('sha256'),
                    'SURFACE_FRAME_INDEX_INVALID')
            self.times.append(row['timeSeconds'])
        require(isinstance(self.result.get('final'), dict)
                and self.times[-1] == catalog.get('finalTimeSeconds') == self.result['final'].get('timeSeconds'),
                'SURFACE_FRAME_COMPLETION_MISMATCH')

    def _binary(self, meta, expected_size):
        require(meta.get('bytes') == expected_size and expected_size <= 32*1024**2
                and self.result['files'].get('native-frames/'+meta['file']) == meta.get('sha256'),
                'SURFACE_FRAME_RESULT_BINDING_INVALID')
        raw = _read(self.root/meta['file'], meta['sha256'], expected_size)
        require(len(raw) == expected_size, 'SURFACE_FRAME_SIZE_MISMATCH')
        return raw

    def visible_triangles(self, bounds):
        require(isinstance(bounds, (list, tuple)) and len(bounds) == 4
                and all(type(v) in (int, float) and math.isfinite(v) for v in bounds)
                and bounds[0] < bounds[2] and bounds[1] < bounds[3], 'SURFACE_FRAME_VIEWPORT_INVALID')
        return self.np.flatnonzero((self.xy_max[:, 0] >= bounds[0]) & (self.xy_max[:, 1] >= bounds[1])
            & (self.xy_min[:, 0] <= bounds[2]) & (self.xy_min[:, 1] <= bounds[3])).tolist()

    def frame(self, index, *, triangles=None):
        np = self.np
        require(type(index) is int and 0 <= index < len(self.times), 'SURFACE_FRAME_INDEX_INVALID')
        row = self.catalog['frames'][index]
        values = np.frombuffer(self._binary(row, self.count*3*8), dtype='<f8').reshape(self.count, 3)
        require(np.all(np.isfinite(values)) and np.min(values[:, 0]) >= -1e-10,
                'SURFACE_FRAME_NONPHYSICAL_STATE')
        storage = float(np.dot(values[:, 0], self.mesh['areas']))
        require(math.isclose(storage, row['storageM3'], abs_tol=1e-10, rel_tol=1e-12),
                'SURFACE_FRAME_STORAGE_MISMATCH')
        if triangles is None:
            triangles = list(range(self.count))
        require(isinstance(triangles, list) and len(triangles) <= self.count
                and all(type(i) is int and 0 <= i < self.count for i in triangles)
                and len(set(triangles)) == len(triangles), 'SURFACE_FRAME_SELECTION_INVALID')
        selected = values[triangles]
        depth, momentum = selected[:, 0], selected[:, 1:]
        velocity = np.divide(momentum, depth[:, None], out=np.zeros_like(momentum),
                             where=depth[:, None] > VELOCITY_DEPTH_M)
        return {'index': index, 'timeSeconds': row['timeSeconds'], 'triangles': triangles,
                'depthM': depth.tolist(), 'velocityXMps': velocity[:, 0].tolist(),
                'velocityYMps': velocity[:, 1].tolist(), 'momentumM2s': momentum.tolist(),
                'wholeDomainStorageM3': row['storageM3'],
                'storageReconstructionResidualM3': storage-row['storageM3'], 'sourceSha256': row['sha256']}

    def at_time(self, seconds, *, triangles=None):
        require(type(seconds) in (int, float) and math.isfinite(seconds), 'SURFACE_FRAME_EXTRAPOLATION_FORBIDDEN')
        at = clamp_clock_roundoff(seconds, self.times[0], self.times[-1], 'SURFACE_FRAME_EXTRAPOLATION_FORBIDDEN')
        index = bisect_right(self.times, at)-1
        # 8 ULP 이내의 시계 반올림만 같은 시각으로 대응하고 실제 출력 시각은 유지한다.
        if index+1 < len(self.times):
            following = self.times[index+1]
            if following-at <= 8*max(math.ulp(at), math.ulp(following)):
                index, at = index+1, following
        result = self.frame(index, triangles=triangles)
        return result | {'requestedTimeSeconds': seconds, 'ageSeconds': at-result['timeSeconds'],
                         'clockRoundoffAdjustmentSeconds': at-seconds,
                         'interpolation': 'NONE_PREVIOUS_RECORDED_STATE'}
