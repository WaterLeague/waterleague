"""원 수치지형도 레코드 해석을 별도 GDAL 드라이버와 대조."""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import shapely
from shapely.geometry import shape

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native

LAYERS = {'N1A_B0010000', 'N1A_A0010000', 'N1L_A0020000', 'N1A_A0033320',
          'N1A_A0070000', 'N1A_A0160024', 'N1A_E0032111', 'N1L_F0010000', 'N1P_F0020000'}
COORDINATE_TOLERANCE_M = 1e-8


def compare(records, features):
    if len(records) != len(features):
        raise source.TopographyDataError('GDAL·원 레코드 수 불일치')
    counts = Counter()
    for record, feature in zip(records, features):
        if feature.get('id') != record['number'] - 1:
            raise source.TopographyDataError('GDAL·원 레코드 번호 불일치')
        item = native.native_geometry(record['rawShape'])
        if item['status'] != 'VALID' or record['deleted']:
            counts['notComparedInvalidOrDeleted'] += 1
            continue
        reference = shape(feature['geometry'])
        if not reference.is_valid:
            raise source.TopographyDataError('유효 판정과 GDAL 도형 불일치')
        actual = item['geometry']
        if not shapely.equals_exact(actual, reference, tolerance=COORDINATE_TOLERANCE_M, normalize=True):
            raise source.TopographyDataError('원 레코드·GDAL 형상 불일치')
        if (not math.isclose(actual.area, reference.area, rel_tol=1e-10, abs_tol=1e-6)
                or not math.isclose(actual.length, reference.length, rel_tol=1e-10, abs_tol=1e-6)):
            raise source.TopographyDataError('원 레코드·GDAL 면적/길이 불일치')
        counts['comparedValidGeometry'] += 1
    return counts


def verify(catalog, executable):
    tiles = catalog.tiles()
    selected = sorted(set([tiles[index][0] for index in range(0, len(tiles), max(1, len(tiles) // 6))]
                          + [tile for tile in ('377052201', '377052202', '377052211', '377052212')
                             if any(entry[0] == tile for entry in tiles)]))
    environment = {key: os.environ[key] for key in ('PATH', 'TMPDIR', 'LANG') if key in os.environ}
    environment.update({'PROJ_NETWORK': 'OFF', 'GDAL_PAM_ENABLED': 'NO', 'OGR_ORGANIZE_POLYGONS': 'ONLY_CCW'})
    counts, layer_counts = Counter(), {}
    with tempfile.TemporaryDirectory(prefix='waterleague-gdal-reference-') as temporary:
        for tile in selected:
            for layer, checksum, metadata, parts in catalog.layers(tile, LAYERS):
                target = Path(temporary) / f'{tile}-{layer}.json'
                subprocess.run([executable, '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', '-preserve_fid',
                    str(target), '/vsizip/' + str(catalog.directory / 'tiles' / (tile + '.zip')), layer],
                    check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=environment)
                if target.stat().st_size > 64 * 1024**2:
                    raise source.TopographyDataError('GDAL 대조 출력 크기 제한 초과')
                features = json.loads(target.read_text())['features']
                records = list(native.records(tile, layer, checksum, metadata, parts))
                result = compare(records, features)
                counts.update(result)
                layer_counts[tile + ':' + layer] = dict(result)
    version = subprocess.run([executable, '--version'], check=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=10, env=environment).stdout.decode().strip()
    return {'schemaVersion': 1, 'sourceCatalogSha256': catalog.summary['catalogSha256'],
            'readerSha256': spatial.file_sha256(native.__file__), 'verifierSha256': spatial.file_sha256(__file__),
            'gdalVersion': version, 'counts': dict(counts), 'selectedTileIds': selected,
            'layerCounts': layer_counts, 'coordinateToleranceM': COORDINATE_TOLERANCE_M,
            'policy': 'VALID_NATIVE_RECORDS_ONLY_NO_REPAIR_OR_REPROJECTION', 'fieldAccuracyValidated': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=source.ROOT / source.OUTPUT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 검증 결과 덮어쓰기 금지')
        executable = shutil.which('ogr2ogr')
        if executable is None:
            raise source.TopographyDataError('별도 GDAL 드라이버 설치 필요')
        catalog = native.SourceCatalog(args.source, native.read_json(spatial.SOURCE_SUMMARY))
        report = verify(catalog, executable)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(report) + '\n')
    except source.TopographyDataError as exc:
        parser.exit(1, f'GDAL 대조 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, shapely.errors.ShapelyError):
        parser.exit(1, 'GDAL 대조 실패: 원본·도구·실행 조건 확인 필요\n')
    print(source.canonical({'counts': report['counts'], 'gdalVersion': report['gdalVersion']}))


if __name__ == '__main__':
    main()
