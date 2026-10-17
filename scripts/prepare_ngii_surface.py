"""보관된 공개 90m DEM의 원본 창을 상대 높이 탐색 격자로 변환."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from audit_spatial_sources import command
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.grid import surface_from_grid

ARCHIVE = ROOT / 'data/private/seongsu-official-20261017/dem-2025.zip'
RASTER = ROOT / 'data/private/seongsu-official-20261017/dem-2025/37705/37705.img'
ARCHIVE_SHA = 'a99a82b4e98f5e26445f88801b95d87b823bfef154db804acbb60fc136683feb'
WINDOW = [48, 247, 13, 13]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def prepare(directory):
    require(not directory.exists(), 'TERRAIN_OUTPUT_EXISTS')
    require(sha(ARCHIVE) == ARCHIVE_SHA, 'TERRAIN_SOURCE_HASH_MISMATCH')
    with zipfile.ZipFile(ARCHIVE) as bundle:
        names = [name for name in bundle.namelist() if name.endswith('/37705.img')]
        require(len(names) == 1 and hashlib.sha256(bundle.read(names[0])).hexdigest() == sha(RASTER),
                'TERRAIN_RASTER_HASH_MISMATCH')
    catalog_manifest = ROOT / 'data/manifests/ngii-elevation-products-20231107.json'
    catalog = json.loads(catalog_manifest.read_bytes())
    for name, expected in catalog['files'].items():
        require(sha(ROOT / name) == expected, 'TERRAIN_CATALOG_HASH_MISMATCH')
    with (ROOT / 'data/raw/ngii-elevation-products-20231107.csv').open(encoding='cp949', newline='') as stream:
        family = [{'sourceRow': index, 'tile': row['도엽번호5000'], 'year': row['원시자료제작년도'],
                   'spacing': row['격자간격'].strip(), 'unit': row['단위'], 'datum': row['표고기준'],
                   'format': row['자료형식']}
                  for index, row in enumerate(csv.DictReader(stream), 2)
                  if row['도엽번호5000'].startswith('37705') and '90' in row['격자간격']]
    require(len(family) == 4 and all(r['unit'].lower() == 'm' for r in family),
            'TERRAIN_UNIT_EVIDENCE_CHANGED')
    info = json.loads(command('gdalinfo', '-json', '-if', 'HFA', RASTER))
    require(info['size'] == [252, 315] and len(info['bands']) == 1
            and info['bands'][0]['type'] == 'Float32', 'TERRAIN_SOURCE_FORMAT_CHANGED')
    xoff, yoff, width, height = WINDOW
    require(xoff + width <= info['size'][0] and yoff + height <= info['size'][1],
            'TERRAIN_WINDOW_OUTSIDE')
    rows = command('gdal_translate', '-q', '-of', 'XYZ', '-ovr', 'NONE', '-srcwin',
                   *WINDOW, RASTER, '/vsistdout/').splitlines()
    triples = [list(map(float, row.split())) for row in rows]
    require(len(triples) == width * height and all(len(row) == 3 for row in triples),
            'TERRAIN_RASTER_ORDER_INVALID')
    transform = list(info['geoTransform'])
    transform[0] += xoff * transform[1]
    transform[3] += yoff * transform[5]
    for index, (x, y, _) in enumerate(triples):
        column, row = index % width, index // width
        require(abs(x - (transform[0] + (column + .5) * transform[1])) < 1e-7
                and abs(y - (transform[3] + (row + .5) * transform[5])) < 1e-7,
                'TERRAIN_RASTER_ORDER_INVALID')
    source_files = {str(ARCHIVE.relative_to(ROOT)): sha(ARCHIVE),
                    str(RASTER.relative_to(ROOT)): sha(RASTER),
                    str(catalog_manifest.relative_to(ROOT)): sha(catalog_manifest)} | catalog['files']
    grid = {'schemaVersion': 1, 'width': width, 'height': height,
            'coordinateWkt': info['coordinateSystem']['wkt'], 'geoTransform': transform,
            'sourcePixelWindow': WINDOW, 'noDataValue': info['bands'][0].get('noDataValue'),
            'values': [row[2] for row in triples], 'sourceFiles': source_files,
            'editionYear': 2025, 'acquisitionDate': None, 'sourceResolutionM': 90,
            'verticalReference': {'unit': 'm', 'unitStatus': 'PRODUCT_FAMILY_INFERRED',
                'unitEvidence': {'source': catalog['sourceUrl'], 'records': family,
                    'limitation': '같은 지역 90m 제품군의 미터 표기; 보관된 2025 파일과 직접 일치 없음'},
                'datum': None, 'datumVerified': False}}
    count = 2 * (width - 1) * (height - 1)
    specification = {'maxStepSeconds': .1, 'manningN': [0.] * count,
        'initialDepthM': [0.] * count, 'rainfallOwner': ['SURFACE'] * count,
        'boundaryConditions': {key: {'type': 'TRANSMISSIVE'} for key in ('north', 'south', 'east', 'west')},
        'evidence': {'roughness': '지형 입력 연결 진단용 마찰 0; 실제 토지피복 조도 아님',
            'initialState': '입력 연결 진단용 건조 시작; 선행 수분·하천 수위 재현 아님',
            'boundary': '사각 창의 전달 경계 시험; 실제 분수계·외부 유입·배수·하천 경계 미확인',
            'rainfallOwner': '독립 지표 입력 시험, 연결 관망 없음'}}
    model = surface_from_grid(grid, specification)
    directory.mkdir(parents=True)
    write(directory / 'raster-info.json', info)
    write(directory / 'grid.json', grid)
    write(directory / 'hydraulic-specification.json', specification)
    write(directory / 'surface-input.json', model)
    sources = [Path(__file__), ROOT / 'scripts/audit_spatial_sources.py',
               ROOT / 'simulation/waterleague_sim/terrain/grid.py', ROOT / 'simulation/uv.lock']
    for source in [*(ROOT / name for name in source_files), *sources]:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': model['evidence'], 'rankingEligible': False,
        'sourceArchiveSha256': ARCHIVE_SHA, 'gridSha256': sha(directory / 'grid.json'),
        'surfaceInputSha256': sha(directory / 'surface-input.json'), 'sourcePixelWindow': WINDOW,
        'vertices': len(model['verticesM']), 'triangles': count,
        'areaM2': (width-1) * transform[1] * (height-1) * -transform[5],
        'heightRangeRaw': [min(grid['values']), max(grid['values'])],
        'gdalVersion': command('gdalinfo', '--version').strip(),
        'verticalReference': grid['verticalReference'],
        'limitations': model['terrainProvenance']['limitations'],
        'sourceCode': {str(path.relative_to(ROOT)): sha(path) for path in sources},
        'files': {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
    write(directory / 'terrain-input-manifest.json', report)
    return model, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, report = prepare(args.output.resolve())
    print(json.dumps({key: report[key] for key in ('vertices', 'triangles', 'areaM2', 'heightRangeRaw',
                                                  'surfaceInputSha256')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
