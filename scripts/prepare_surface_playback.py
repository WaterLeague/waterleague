"""완료 지표 결과의 지도 전달 묶음 생성. 운영 작업·순위 등록 없음."""
import argparse
import json
from pathlib import Path
import shutil

from waterleague_sim.engine.surface_frame_reader import NativeFrameReader
from waterleague_sim.engine.surface_frames import encode, sha
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.presentation.surface_playback import export_playback
from waterleague_sim.presentation.surface_directions import flow_direction

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--result-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preview-index', type=int)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('기존 출력 덮어쓰기 거부')
    city = json.loads((ROOT/'frontend/public/data/seoul-v1/city.json').read_bytes())
    descriptor = export_playback(args.source, args.result_sha256, args.output/'surface-playback', city)
    (args.output/'publication.json').write_bytes(encode(descriptor))
    catalog = json.loads((args.output/'surface-playback/catalog.json').read_bytes())
    mesh = json.loads((args.output/'surface-playback/mesh.json').read_bytes())
    reader = NativeFrameReader(args.source, args.result_sha256)
    if args.preview_index is not None:
        frame = reader.frame(args.preview_index)
        display = {key: catalog[key] for key in ('schemaVersion','surfaceResultSha256','classification',
            'startUtc','coordinateSystem','originProjected','verticalPlacement','triangleCount','limitations',
            'flowDirectionMethod')}
        display.update(catalogSha256=descriptor['catalogSha256'], timesSeconds=reader.times)
        value = {'catalogSha256':descriptor['catalogSha256'], 'sourceSha256':frame['sourceSha256'],
            'index':frame['index'], 'timeSeconds':frame['timeSeconds'], 'wholeDomainStorageM3':frame['wholeDomainStorageM3'],
            'cells':[{'triangleId':i, 'vertices':[mesh['vertices'][v] for v in t], 'depthM':frame['depthM'][i],
                'speedMps':(frame['velocityXMps'][i]**2+frame['velocityYMps'][i]**2)**.5,
                'flowDirection':flow_direction(mesh['directionBasis'][i], frame['velocityXMps'][i],
                                              frame['velocityYMps'][i], frame['depthM'][i])}
                for i,t in enumerate(mesh['triangles'])]}
        (args.output/'preview.json').write_bytes(encode({'catalog':display,'frame':value}))
    sources = [Path(__file__), ROOT/'simulation/waterleague_sim/presentation/surface_playback.py',
               ROOT/'simulation/waterleague_sim/presentation/surface_directions.py',
               ROOT/'simulation/waterleague_sim/engine/surface_frame_reader.py',
               ROOT/'simulation/waterleague_sim/engine/surface_frames.py',
               ROOT/'simulation/waterleague_sim/engine/flood_errors.py',
               ROOT/'simulation/waterleague_sim/forcing/stage.py',
               ROOT/'simulation/waterleague_sim/forcing/__init__.py',
               ROOT/'simulation/waterleague_sim/terrain/coverage.py',
               ROOT/'simulation/waterleague_sim/terrain/grid.py',
               ROOT/'simulation/waterleague_sim/terrain/__init__.py',
               ROOT/'simulation/waterleague_sim/presentation/__init__.py',
               ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock',
               ROOT/'frontend/public/data/seoul-v1/city.json']
    for source in sources:
        target = args.output/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    # 지도 전달을 재생하는 입력만 보존하며 물리 계산 전체를 재실행한 것으로 표시하지 않는다.
    native_files = ['surface-result.json', 'surface-input.json', 'native-frames/catalog.json']
    native_files += ['native-frames/'+m['file'] for m in reader.catalog['mesh'].values()]
    native_files += ['native-frames/'+m['file'] for m in reader.catalog['frames']]
    for name in native_files:
        raw = (args.source/name).read_bytes()
        expected = args.result_sha256 if name == 'surface-result.json' else reader.result['files'][name]
        require(sha(raw) == expected, 'SURFACE_FRAME_HASH_MISMATCH')
        target = args.output/'input/surface'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    files = {str(p.relative_to(args.output)): sha(p.read_bytes()) for p in sorted(args.output.rglob('*')) if p.is_file()}
    manifest = encode({'schemaVersion':1, 'replayScope':'PLAYBACK_EXPORT_ONLY',
        'surfaceResultSha256':args.result_sha256,'files':files})
    (args.output/'manifest.json').write_bytes(manifest)
    print(json.dumps({'catalogSha256':descriptor['catalogSha256'],'manifestSha256':sha(manifest),
                     'frames':len(catalog['frames']),'triangles':catalog['triangleCount']},ensure_ascii=False))


if __name__ == '__main__':
    main()
