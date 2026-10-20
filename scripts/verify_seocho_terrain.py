"""서초 파생 지형의 관측 강우 실행·시간/공간 해상도·재현 검사."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))

from prepare_seocho_terrain import sha, write
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.terrain.contours import ContourTin, surface_from_contours
from waterleague_sim.terrain.grid import digest


def verify_sources(directory):
    report = json.loads((directory/'manifest.json').read_bytes())
    for relative, expected in report['files'].items():
        path = directory/relative
        require(path.resolve().is_relative_to(directory) and not path.is_symlink()
                and sha(path) == expected, 'SEOCHO_TERRAIN_BUNDLE_CHANGED')
    tin = ContourTin(json.loads((directory/'source-records.json').read_bytes()))
    require(tin.identity == report['tinSha256']
            and digest(json.loads((directory/'tin.json').read_bytes())) == tin.identity,
            'SEOCHO_TERRAIN_TIN_REPLAY_CHANGED')
    for row in report['grids']:
        key = f"{int(row['spacingM'])}m"
        grid = json.loads((directory/f'grid-{key}.json').read_bytes())
        replay = tin.grid(report['domainBounds'], row['spacingM'], grid['sourceFiles'], grid['verticalReference'])
        require(replay == grid, 'SEOCHO_TERRAIN_GRID_REPLAY_CHANGED')
        model = surface_from_contours(grid, json.loads((directory/f'specification-{key}.json').read_bytes()))
        require(model == json.loads((directory/f'surface-{key}.json').read_bytes()),
                'SEOCHO_TERRAIN_SURFACE_REPLAY_CHANGED')
    return report


def rainfall(model, minutes):
    start = datetime(2022, 8, 8, 9, tzinfo=timezone.utc)
    return {'schemaVersion': 1, 'startUtc': start.isoformat(),
        'endUtc': (start+timedelta(minutes=minutes)).isoformat(),
        'assignmentEvidence': '서초 AWS 401 관측을 유역 주변 지형 창에 균일 배정; 면적 평균 실측·당시 침수 복원 아님',
        'stations': [{'file': 'kma-401-202208081800-202208082359-disaster-v1.json',
                      'sha256': '39ce4686facc74c09f13c2911162ea0293a30a8cac410da821a5fa51a423f21c'}],
        'stationByTriangle': ['401']*len(model['triangles'])}


def compact(result):
    final = result['final']
    return {'numericalStatus': result['numericalStatus'], 'observedRainfall': result['observedRainfall'],
        'numericalQuality': result['numericalQuality'], 'numericalConfiguration': result['numericalConfiguration'],
        'maximumForcingBoundaryBalanceResidualM3': result['maximumForcingBoundaryBalanceResidualM3'],
        'final': {k: v for k, v in final.items() if k not in ('depthM', 'velocityXMps', 'velocityYMps')},
        'maximumFinalDepthM': max(final['depthM']),
        'maximumFinalSpeedMps': max(math.hypot(x, y) for x, y in zip(final['velocityXMps'], final['velocityYMps']))}


def spatial_comparison(coarse, fine, coarse_depth, fine_depth):
    import shapely
    from shapely.geometry import Polygon
    polygons = [Polygon([coarse['verticesM'][j] for j in t]) for t in coarse['triangles']]
    tree = shapely.STRtree(polygons)
    volumes, areas = [0.]*len(polygons), [0.]*len(polygons)
    for triangle, depth in zip(fine['triangles'], fine_depth, strict=True):
        polygon = Polygon([fine['verticesM'][j] for j in triangle])
        indexes = tree.query(polygon.centroid, predicate='covered_by')
        require(len(indexes) == 1, 'SEOCHO_TERRAIN_MESH_COMPARISON_AMBIGUOUS')
        i = int(indexes[0])
        require(polygons[i].covers(polygon), 'SEOCHO_TERRAIN_MESH_COMPARISON_OUTSIDE')
        volumes[i] += depth*polygon.area
        areas[i] += polygon.area
    require(all(a == p.area for a, p in zip(areas, polygons, strict=True)), 'SEOCHO_TERRAIN_MESH_AREA_MISMATCH')
    differences = [d-v/a for d, v, a in zip(coarse_depth, volumes, areas, strict=True)]
    return {'method': 'FINE_TRIANGLE_AREA_MEAN_ON_IDENTICAL_COARSE_TRIANGLES',
        'maximumAbsoluteFinalDepthDifferenceM': max(map(abs, differences)),
        'areaWeightedMeanAbsoluteFinalDepthDifferenceM':
            math.fsum(abs(d)*a for d, a in zip(differences, areas))/math.fsum(areas)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--terrain', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--minutes', type=int, default=60)
    args = parser.parse_args()
    source, output = args.terrain.resolve(), args.output.resolve()
    require(1 <= args.minutes <= 359 and not output.exists(), 'SEOCHO_TERRAIN_VERIFICATION_ARGUMENTS')
    terrain = verify_sources(source)
    output.mkdir(parents=True)
    shutil.copytree(source, output/'terrain')
    sources = [Path(__file__), ROOT/'scripts/prepare_seocho_terrain.py']
    for folder in ('engine', 'forcing', 'ingestion', 'terrain'):
        sources.extend(sorted((ROOT/'simulation/waterleague_sim'/folder).glob('*.py')))
    for path in sources:
        target = output/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    report = {'schemaVersion': 1, 'classification': terrain['classification'], 'rankingEligible': False,
        'terrainManifestSha256': sha(source/'manifest.json'), 'terrain': {k: v for k, v in terrain.items() if k != 'files'},
        'minutes': args.minutes, 'exactTerrainReplay': True, 'cases': [],
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources}}
    results, models = {}, {}
    for name, spacing, step, boundary in [('20m-1s', 20, 1., 'TRANSMISSIVE'),
            ('20m-05s', 20, .5, 'TRANSMISSIVE'), ('10m-1s', 10, 1., 'TRANSMISSIVE'),
            ('20m-replay', 20, 1., 'TRANSMISSIVE'), ('20m-closed', 20, 1., 'REFLECTIVE')]:
        model = json.loads((source/f'surface-{spacing}m.json').read_bytes())
        model['maxStepSeconds'] = step
        model['boundaryConditions'] = {k: {'type': boundary} for k in model['boundaryConditions']}
        if boundary == 'REFLECTIVE':
            model['terrainProvenance']['fieldEvidence']['boundary'] = '같은 사각 창의 전면 차단 경계 민감도; 실제 벽 아님'
        models[name] = model
        row = {'name': name, 'calculationSpacingM': spacing, 'maximumStepSeconds': step, 'boundary': boundary}
        print(json.dumps({'started': name}, ensure_ascii=False), flush=True)
        try:
            result = run_observed_surface(model, rainfall(model, args.minutes), output/name)
            results[name] = result
            row.update(compact(result), resultSha256=sha(output/name/'observed-surface-result.json'))
        except FloodModelError as error:
            row.update(numericalStatus='FAILED', code=str(error))
        report['cases'].append(row)
        write(output/'progress.json', report)
        print(json.dumps({'finished': name, 'status': row['numericalStatus'],
                          'maximumFinalDepthM': row.get('maximumFinalDepthM')}, ensure_ascii=False), flush=True)
    if all(name in results for name in models):
        a, b, fine, replay, closed = [results[k]['final'] for k in models]
        report['timeComparison'] = {'maximumStepsSeconds': [1., .5],
            'maximumAbsoluteFinalDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
            'storageDifferenceM3': a['storageM3']-b['storageM3']}
        report['spatialComparison'] = spatial_comparison(models['20m-1s'], models['10m-1s'], a['depthM'], fine['depthM'])
        report['spatialComparison']['storageDifferenceM3'] = a['storageM3']-fine['storageM3']
        report['exactHydraulicReplay'] = a == replay
        report['boundarySensitivity'] = {'closedMinusOpenFinalStorageM3': closed['storageM3']-a['storageM3']}
        require(report['exactHydraulicReplay'], 'SEOCHO_TERRAIN_HYDRAULIC_REPLAY_CHANGED')
    report['limitations'] = terrain['limitations']+[
        '2026 배포 지형과 2022 관측 강우의 탐색 계산; 2022 현장 침수 재현 아님',
        '불투수면 조도 일괄·건조 시작·침투/증발/건물 차폐/관망 미포함',
        '최종 수심·유속과 물수지의 수치 비교; 게임 순위·피해액에 미반영']
    report['files'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write(output/'manifest.json', report)
    require(all(row['numericalStatus'] == 'PASSED' for row in report['cases']), 'SEOCHO_TERRAIN_HYDRAULICS_FAILED')
    print(json.dumps({k: report[k] for k in ('timeComparison', 'spatialComparison', 'boundarySensitivity',
                                          'exactHydraulicReplay')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
