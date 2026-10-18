"""보관 성동 DEM 전체에서 기존 성수 계산 창의 외부 배수 기여 확인."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from audit_spatial_sources import command
from prepare_ngii_surface import prepare, RASTER, WINDOW, sha, write
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.drainage import analyze, window_context


def prepare_drainage(directory):
    require(not directory.exists(), 'DRAINAGE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    prepare(directory / 'reference-window')
    reference = json.loads((directory / 'reference-window/grid.json').read_bytes())
    info = json.loads((directory / 'reference-window/raster-info.json').read_bytes())
    width, height = info['size']
    transform = info['geoTransform']
    lines = command('gdal_translate', '-q', '-of', 'XYZ', '-ovr', 'NONE', RASTER, '/vsistdout/').splitlines()
    require(len(lines) == width * height, 'DRAINAGE_SOURCE_DIMENSIONS_CHANGED')
    values = []
    for i, line in enumerate(lines):
        row = list(map(float, line.split()))
        require(len(row) == 3, 'DRAINAGE_RASTER_ORDER_INVALID')
        r, c = divmod(i, width)
        require(abs(row[0] - (transform[0] + (c + .5) * transform[1])) < 1e-7
                and abs(row[1] - (transform[3] + (r + .5) * transform[5])) < 1e-7,
                'DRAINAGE_RASTER_ORDER_INVALID')
        values.append(row[2])
    grid = deepcopy(reference)
    grid.update(width=width, height=height, geoTransform=transform,
                sourcePixelWindow=[0, 0, width, height], values=values)
    # 같은 원본 창의 모든 높이를 대조해 다른 판본·리샘플링 혼입을 막는다.
    x, y, w, h = WINDOW
    require([values[r * width + c] for r in range(y, y + h) for c in range(x, x + w)]
            == reference['values'], 'DRAINAGE_SOURCE_WINDOW_CHANGED')
    original = deepcopy(grid)
    analysis = analyze(grid)
    context = window_context(grid, analysis, WINDOW)
    require(grid == original and analyze(grid) == analysis, 'DRAINAGE_REPLAY_CHANGED')
    write(directory / 'grid.json', grid)
    write(directory / 'drainage.json', analysis)
    write(directory / 'reference-window-context.json', context)
    def xy(i):
        r, c = divmod(i, width)
        return [transform[0] + (c + .5) * transform[1], transform[3] + (r + .5) * transform[5]]
    # 원 투영 좌표를 유지하며 GeoJSON에 WGS84 좌표라고 표시하지 않는다.
    paths = {'schemaVersion': 1, 'coordinateWkt': grid['coordinateWkt'],
        'sourceGridSha256': analysis['sourceGridSha256'], 'method': analysis['method'],
        'incomingPaths': [{'fromCell': a, 'toCell': b, 'coordinates': [xy(a), xy(b)],
            'fromElevationM': values[a], 'toElevationM': values[b],
            'contributingAreaM2': analysis['contributingCellsIncludingSelf'][a] * analysis['cellAreaM2']}
            for a, b in context['incomingLinks']],
        'limitations': analysis['limitations']}
    write(directory / 'incoming-paths.json', paths)
    sources = [Path(__file__), ROOT / 'simulation/waterleague_sim/terrain/drainage.py',
               ROOT / 'simulation/waterleague_sim/terrain/grid.py',
               ROOT / 'simulation/waterleague_sim/terrain/__init__.py',
               ROOT / 'simulation/waterleague_sim/engine/flood_errors.py',
               ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock']
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': analysis['classification'], 'rankingEligible': False,
        'sourceRasterSha256': sha(RASTER), 'sourceGridSha256': analysis['sourceGridSha256'],
        'method': analysis['method'], 'sourceReference': analysis['sourceReference'],
        'summary': analysis['summary'],
        'referenceWindow': {key: value for key, value in context.items()
            if key not in ('incomingLinks', 'outgoingLinks', 'outsideContributingCells')},
        'incomingLinkCount': len(context['incomingLinks']), 'outgoingLinkCount': len(context['outgoingLinks']),
        'outsideContributingCellCount': len(context['outsideContributingCells']),
        'exactReplay': True, 'originalWindowElevationsExact': True,
        'limitations': analysis['limitations'],
        'files': {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
    write(directory / 'manifest.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = prepare_drainage(args.output.resolve())
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))
