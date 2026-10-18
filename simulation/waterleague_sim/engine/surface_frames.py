"""계산 중심값의 제한된 이진 프레임 기록. 물리 상태와 시간 간격 변경 없음."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require

FIELDS = ['depthM', 'xmomentumM2s', 'ymomentumM2s']
VELOCITY_DEPTH_M = 1e-6


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode()


class NativeFrameWriter:
    def __init__(self, domain, model, directory):
        import numpy as np
        spec = model.get('frameOutput')
        require(isinstance(spec, dict) and type(spec.get('schemaVersion')) is int and spec['schemaVersion'] == 1
                and spec.get('type') == 'NATIVE_CENTROID_FLOAT64'
                and type(spec.get('maxFrames')) is int and 2 <= spec['maxFrames'] <= 10000
                and type(spec.get('maxBytes')) is int and 1 <= spec['maxBytes'] <= 512*1024**2,
                'SURFACE_FRAME_SPECIFICATION_INVALID')
        self.np, self.domain, self.spec = np, domain, spec
        self.directory = Path(directory)
        require(not self.directory.exists(), 'SURFACE_FRAME_OUTPUT_EXISTS')
        self.directory.mkdir(parents=True)
        self.frames, self.bytes = [], 0
        self.closed = False
        arrays = {
            'vertices': (np.column_stack((model['verticesM'], model['elevationM'])), '<f8'),
            'triangles': (np.asarray(model['triangles']), '<u4'),
            'centroids': (np.column_stack((domain.centroid_coordinates,
                domain.quantities['elevation'].centroid_values)), '<f8'),
            'areas': (domain.areas, '<f8')}
        mesh = {}
        for name, (values, dtype) in arrays.items():
            array = np.ascontiguousarray(values, dtype=dtype)
            mesh[name] = self._write(name + '.bin', array.tobytes()) | {'dtype': dtype, 'shape': list(array.shape)}
        self.catalog = {'schemaVersion': 1, 'type': 'NATIVE_CENTROID_FLOAT64',
            'classification': model['evidence'], 'rankingEligible': False,
            'coordinateSystem': model['coordinateSystem'], 'verticalDatum': model['verticalDatum'],
            'terrainProvenance': model.get('terrainProvenance'), 'startUtc': model.get('startUtc'),
            'vertexCount': len(model['verticesM']), 'triangleCount': len(model['triangles']),
            'modelSha256': sha(encode(model)), 'inputFileSha256': sha((self.directory.parent/'surface-input.json').read_bytes()),
            'mesh': mesh, 'frameFields': FIELDS, 'frameDtype': '<f8', 'frames': self.frames,
            'velocityDepthThresholdM': VELOCITY_DEPTH_M, 'timeInterpolation': 'NONE_PREVIOUS_RECORDED_STATE',
            'timePolicy': 'ACTUAL_NATIVE_TIME_FIRST_RECORD_AT_EACH_TIME',
            'sourceCodeSha256': sha(Path(__file__).read_bytes()),
            'limitations': ['저장 시각의 격자 중심 계산값; 관측 침수·현장 측량값 아님',
                '프레임에서 물리 첨두·지속시간·점수 재계산 금지',
                '좌표/수직 기준 미확인을 화면 위치 추정으로 대체하지 않음']}

    def _write(self, name, raw):
        require(self.bytes + len(raw) <= self.spec['maxBytes'], 'SURFACE_FRAME_BYTE_LIMIT_EXCEEDED')
        with (self.directory/name).open('xb') as stream:
            stream.write(raw)
        self.bytes += len(raw)
        return {'file': name, 'sha256': sha(raw), 'bytes': len(raw)}

    def record(self):
        require(not self.closed, 'SURFACE_FRAME_WRITER_CLOSED')
        np, domain = self.np, self.domain
        now = float(domain.get_time())
        require(math.isfinite(now) and now >= 0, 'SURFACE_FRAME_TIME_INVALID')
        if self.frames and now == self.frames[-1]['timeSeconds']:
            return
        require(not self.frames or now > self.frames[-1]['timeSeconds'], 'SURFACE_FRAME_TIME_REVERSED')
        require(len(self.frames) < self.spec['maxFrames'], 'SURFACE_FRAME_COUNT_LIMIT_EXCEEDED')
        depth = domain.quantities['stage'].centroid_values - domain.quantities['elevation'].centroid_values
        momentum = np.column_stack([domain.quantities[k].centroid_values for k in ('xmomentum', 'ymomentum')])
        require(np.all(np.isfinite(depth)) and np.all(np.isfinite(momentum)) and np.min(depth) >= -1e-10,
                'SURFACE_FRAME_NONPHYSICAL_STATE')
        values = np.ascontiguousarray(np.column_stack((depth, momentum)), dtype='<f8')
        velocity = np.divide(momentum, depth[:, None], out=np.zeros_like(momentum),
                             where=depth[:, None] > VELOCITY_DEPTH_M)
        row = self._write(f'frame-{len(self.frames):05d}.bin', values.tobytes())
        row.update(index=len(self.frames), timeSeconds=now, storageM3=float(np.dot(depth, domain.areas)),
            minimumDepthM=float(np.min(depth)), maximumDepthM=float(np.max(depth)),
            maximumDisplaySpeedMps=float(np.max(np.linalg.norm(velocity, axis=1))))
        self.frames.append(row)

    def finish(self, numerical_status):
        require(numerical_status in ('PASSED', 'FAILED'), 'SURFACE_FRAME_STATUS_INVALID')
        self.record()
        self.catalog.update(numericalStatus=numerical_status, frameCount=len(self.frames),
                            finalTimeSeconds=self.frames[-1]['timeSeconds'], binaryBytes=self.bytes)
        raw = encode(self.catalog)
        descriptor = self._write('catalog.json', raw)
        self.closed = True
        return {'catalogFile': 'native-frames/catalog.json', 'sha256': descriptor['sha256'],
                'frameCount': len(self.frames), 'triangleCount': self.catalog['triangleCount'],
                'type': self.catalog['type'], 'rankingEligible': False}
