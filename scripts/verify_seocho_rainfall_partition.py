"""공개 서초 집수 경계와 파생 지형의 강우 분할·실제 ANUGA 재생 검사."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))

from prepare_seocho_terrain import sha, write, GEOREFERENCE_SHA
from verify_seocho_terrain import rainfall, compact, spatial_comparison
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.terrain.rainfall_coverage import bind, METHOD, rainfall_difference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--terrain', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    terrain, output = args.terrain.resolve(), args.output.resolve()
    require(not output.exists() and not output.is_relative_to(terrain), 'PARTITION_OUTPUT_INVALID')
    previous = json.loads((ROOT/'data/benchmarks/seocho-terrain-v1.json').read_bytes())
    manifest = json.loads((terrain/'manifest.json').read_bytes())
    require(sha(terrain/'manifest.json') == previous['terrainManifestSha256'], 'PARTITION_TERRAIN_CHANGED')
    for name, expected in manifest['files'].items():
        path = terrain/name
        require(path.resolve().is_relative_to(terrain) and not path.is_symlink()
                and sha(path) == expected, 'PARTITION_TERRAIN_CHANGED')
    geo_path = ROOT/'backend/src/main/resources/watersheds/seocho-georeference-v1.json'
    require(sha(geo_path) == GEOREFERENCE_SHA, 'PARTITION_GEOREFERENCE_CHANGED')
    geo = json.loads(geo_path.read_bytes())
    raw = (terrain/'original-network.inp').read_text()
    require(sha(terrain/'original-network.inp') == geo['sourceOriginalSha256'], 'PARTITION_NETWORK_CHANGED')
    network = {'inputText': raw, 'coordinateSystem': geo['horizontalCrs']}
    specification = {'schemaVersion': 1, 'method': METHOD, 'coordinateSystem': geo['horizontalCrs'],
        'source': {'reference': str(geo_path.relative_to(ROOT)), 'sha256': GEOREFERENCE_SHA},
        'evidence': '공개 연구 모형의 원 집수 도형; 도로 대조 EPSG:5181 가정→5186 변환, 현장 검증 아님',
        'catchments': [{'id': r['id'], 'geometry': {'type': 'Polygon', 'coordinates': [r['points']]}}
                       for r in geo['catchments']]}
    output.mkdir(parents=True)
    shutil.copytree(terrain, output/'terrain')
    shutil.copyfile(geo_path, output/'georeference.json')
    sources = [Path(__file__), ROOT/'scripts/verify_seocho_terrain.py', ROOT/'scripts/prepare_seocho_terrain.py']
    sources += sorted((ROOT/'simulation/waterleague_sim').rglob('*.py'))
    for path in sources:
        target = output/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    results, models, partitions, full = {}, {}, {}, {}
    for spacing in (20, 10):
        original = json.loads((terrain/f'surface-{spacing}m.json').read_bytes())
        from pyproj import CRS
        provenance = original['terrainProvenance']
        require(CRS.from_wkt(provenance['coordinateWkt']) == CRS(geo['horizontalCrs']), 'PARTITION_CRS_MISMATCH')
        origin = provenance['originProjected']
        local = deepcopy(specification)
        local['coordinateSystem'] = original['coordinateSystem']
        local['coordinateOperation'] = {'method': 'SUBTRACT_VERIFIED_PROJECTED_MESH_ORIGIN',
            'sourceCrs': geo['horizontalCrs'], 'originProjected': origin}
        for row in local['catchments']:
            row['geometry']['coordinates'] = [[[x-origin[0], y-origin[1]]
                                               for x, y in ring] for ring in row['geometry']['coordinates']]
        local_network = network | {'coordinateSystem': original['coordinateSystem']}
        model, coverage = bind(original, local_network, local)
        replay, again = bind(original, local_network, local)
        require(replay == model and again == coverage, 'PARTITION_REPLAY_CHANGED')
        models[spacing], partitions[spacing] = model, coverage
        write(output/f'coverage-{spacing}m.json', coverage)
        write(output/f'surface-{spacing}m.json', model)
        spec = rainfall(model, 60)
        spec['stationByTriangle'] = ['401' if v else None for v in coverage['surfaceFractions']]
        write(output/f'rainfall-{spacing}m.json', spec)
        result = run_observed_surface(model, spec, output/f'{spacing}m')
        require(result['numericalStatus'] == 'PASSED', 'PARTITION_SURFACE_NUMERICAL_FAILURE')
        full[spacing] = result
        depth = result['observedRainfall']['stations'][0]['depthMm']
        results[f'{spacing}m'] = compact(result) | {
            'partition': coverage['totals'], 'partialTriangles': sum(0 < f < 1 for f in coverage['surfaceFractions']),
            'declaredAreaRainfallDifference': rainfall_difference(coverage,
                {row['id']: depth for row in coverage['catchments']}),
            'expectedNetworkDeclaredRainfallM3': depth*coverage['totals']['networkDeclaredAreaM2']/1000,
            'expectedCombinedRainfallM3': depth*coverage['totals']['combinedForcingAreaM2']/1000,
            'nativeNetworkExecuted': False}
        write(output/'progress.json', results)
        print(json.dumps({'case': f'{spacing}m', 'status': result['numericalStatus'],
                          'rainM3': result['observedRainfall']['appliedSurfaceRainfallM3']}), flush=True)
    replay = run_observed_surface(models[20], json.loads((output/'rainfall-20m.json').read_bytes()), output/'20m-replay')
    require(replay['final'] == full[20]['final'] and replay['observedRainfall'] == full[20]['observedRainfall'],
            'PARTITION_HYDRAULIC_REPLAY_CHANGED')
    comparison = spatial_comparison(models[20], models[10], full[20]['final']['depthM'], full[10]['final']['depthM'])
    comparison['storageDifferenceM3'] = full[20]['final']['storageM3']-full[10]['final']['storageM3']
    report = {'schemaVersion': 1, 'method': METHOD, 'classification': 'PUBLIC_GEOMETRY_OBSERVED_RAIN_NUMERICAL_CHECK',
        'rankingEligible': False, 'terrainManifestSha256': sha(terrain/'manifest.json'),
        'georeferenceSha256': GEOREFERENCE_SHA, 'networkSha256': sha(terrain/'original-network.inp'),
        'minutes': 60, 'exactPartitionReplay': True, 'exactHydraulicReplay': True,
        'cases': results, 'spatialComparison': comparison,
        'catchments': [{k: v for k, v in r.items() if k != 'intersections'}
                       for r in partitions[20]['catchments']],
        'sourceCode': {str(p.relative_to(ROOT)): sha(output/'source'/p.relative_to(ROOT)) for p in sources},
        'limitations': ['2026 배포 지형과 2022 관측 강우; 당시 침수 복원 아님',
            '원 모형 90.164575ha와 지도 면적 차이를 유지하며 강우를 정규화하지 않음',
            '303ha 지형 창의 미피복 면적은 연구 관망 밖도 포함하며 실제 유역 경계 아님',
            '전달 경계의 순유입·균일 조도·건조 초기 상태는 이전 지형 입력 검사와 동일',
            '공개 지형 실행에는 관망·침투·증발 미연결; 결합/토양은 별도 합성 진단으로 검증',
            '수두 기준·경계·건물/피복과 게임 연결은 후속 구현이며 공식 점수 미반영']}
    write(output/'report.json', report)
    write(output/'manifest.json', {'schemaVersion': 1, 'files': {
        str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    print(json.dumps({'report': str(output/'report.json'), 'manifestSha256': sha(output/'manifest.json')}))


if __name__ == '__main__':
    main()
