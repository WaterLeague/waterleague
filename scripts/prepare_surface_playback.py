"""완료 지표 결과의 지도 전달 묶음 생성. 운영 작업·순위 등록 없음."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from waterleague_sim.engine.surface_frame_reader import NativeFrameReader
from waterleague_sim.engine.surface_frames import encode, sha
from waterleague_sim.presentation.surface_playback import export_playback

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
    if args.preview_index is not None:
        reader = NativeFrameReader(args.source, args.result_sha256)
        frame = reader.frame(args.preview_index)
        display = {key: catalog[key] for key in ('schemaVersion','surfaceResultSha256','classification',
            'startUtc','coordinateSystem','originProjected','verticalPlacement','triangleCount','limitations')}
        display.update(catalogSha256=descriptor['catalogSha256'], timesSeconds=reader.times)
        value = {'catalogSha256':descriptor['catalogSha256'], 'sourceSha256':frame['sourceSha256'],
            'index':frame['index'], 'timeSeconds':frame['timeSeconds'], 'wholeDomainStorageM3':frame['wholeDomainStorageM3'],
            'cells':[{'triangleId':i, 'vertices':[mesh['vertices'][v] for v in t], 'depthM':frame['depthM'][i],
                'speedMps':(frame['velocityXMps'][i]**2+frame['velocityYMps'][i]**2)**.5}
                for i,t in enumerate(mesh['triangles'])]}
        (args.output/'preview.json').write_bytes(encode({'catalog':display,'frame':value}))
    sources = [Path(__file__), ROOT/'simulation/waterleague_sim/presentation/surface_playback.py',
               ROOT/'simulation/waterleague_sim/engine/surface_frame_reader.py',
               ROOT/'simulation/waterleague_sim/engine/surface_frames.py',
               ROOT/'simulation/waterleague_sim/terrain/coverage.py']
    for source in sources:
        target = args.output/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    files = {str(p.relative_to(args.output)): sha(p.read_bytes()) for p in sorted(args.output.rglob('*')) if p.is_file()}
    manifest = encode({'schemaVersion':1,'surfaceResultSha256':args.result_sha256,'files':files})
    (args.output/'manifest.json').write_bytes(manifest)
    print(json.dumps({'catalogSha256':descriptor['catalogSha256'],'manifestSha256':sha(manifest),
                     'frames':len(catalog['frames']),'triangles':catalog['triangleCount']},ensure_ascii=False))


if __name__ == '__main__':
    main()
