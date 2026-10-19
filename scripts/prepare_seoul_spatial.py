"""서울 원 레코드의 도형·속성·출처를 같은 공간 카탈로그로 정규화."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import zipfile
import zlib

import shapely

import prepare_seoul_topography as source
import topography_catalog as native

OUTPUT = source.ROOT / 'data/private/vworld-seoul-topography-20260307/spatial-v1'
SOURCE_SUMMARY = source.ROOT / 'data/manifests/seoul-topography-catalog-v1.json'


def schema_comparison(metadata, layer, semantics):
    entry = semantics['layers'][layer]
    actual = {field['name']: field for field in metadata['dbf']['fields']}
    normalize = lambda value: re.sub(r'[\s․·]', '', value)
    by_label = {normalize(name): name for name in actual}
    matched, missing, expected = {}, [], set()
    for page in entry['manualFieldTablePages']:
        for field in semantics['fieldTablesByPage'][str(page)]:
            label = semantics['fieldLabelAliases'].get(field['label'], field['label'])
            match = by_label.get(normalize(label))
            expected.add(field['id'])
            if match is None:
                missing.append(field['id'])
            else:
                matched[field['id']] = match
    return {'manualMatchedFields': matched, 'missingManualFields': sorted(set(missing)),
            'extraActualFields': sorted(set(actual) - set(matched.values())),
            'manualTableAvailable': bool(expected), 'actualSchema': metadata['dbf']['fields']}


def create_database(connection):
    connection.executescript('''
        PRAGMA foreign_keys=ON;
        PRAGMA page_size=4096;
        PRAGMA cache_size=-65536;
        PRAGMA user_version=1;
        CREATE TABLE tiles(tile TEXT PRIMARY KEY,sha256 TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE layers(tile TEXT NOT NULL REFERENCES tiles(tile),layer TEXT NOT NULL,
            role TEXT NOT NULL,scale_denominator INTEGER NOT NULL,metadata TEXT NOT NULL,
            PRIMARY KEY(tile,layer)) WITHOUT ROWID;
        CREATE TABLE features(fid INTEGER PRIMARY KEY,tile TEXT NOT NULL,layer TEXT NOT NULL,
            record_number INTEGER NOT NULL,raw_shape_sha256 TEXT NOT NULL,raw_dbf_sha256 TEXT NOT NULL,
            properties TEXT NOT NULL,deleted INTEGER NOT NULL,geometry_wkb BLOB,
            geometry_status TEXT NOT NULL,geometry_detail TEXT,part_mapping TEXT NOT NULL,
            minx REAL,miny REAL,maxx REAL,maxy REAL,area_m2 REAL,length_m REAL,
            FOREIGN KEY(tile,layer) REFERENCES layers(tile,layer),UNIQUE(tile,layer,record_number));
        CREATE VIRTUAL TABLE feature_bounds USING rtree(fid,minx,maxx,miny,maxy);
    ''')


def file_sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(catalog, output, progress=None):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 출력·출력 링크 덮어쓰기 금지')
    output.mkdir(mode=0o700)
    try:
        code_files = {'generatorSha256': Path(__file__), 'readerSha256': Path(native.__file__),
                      'sourceReaderSha256': Path(source.__file__)}
        code_hashes = {key: file_sha256(path) for key, path in code_files.items()}
        counts, layer_counts = Counter(), defaultdict(Counter)
        code_counts = defaultdict(lambda: defaultdict(Counter))
        code_examples = defaultdict(lambda: defaultdict(Counter))
        numeric_counts = defaultdict(lambda: defaultdict(Counter))
        numeric_ranges = defaultdict(dict)
        schemas, invalid_reasons = defaultdict(dict), defaultdict(Counter)
        tiles = catalog.tiles()
        with closing(sqlite3.connect(output / 'spatial.sqlite')) as connection:
            create_database(connection)
            fid = 0
            for processed, (tile, checksum, _) in enumerate(tiles, 1):
                connection.execute('INSERT INTO tiles VALUES(?,?)', (tile, checksum))
                for layer, tile_sha256, metadata, components in catalog.layers(tile):
                    meaning = catalog.semantics['layers'][layer]
                    comparison = schema_comparison(metadata, layer, catalog.semantics)
                    schema_key = source.digest(source.canonical(comparison).encode())
                    schemas[layer][schema_key] = comparison
                    connection.execute('INSERT INTO layers VALUES(?,?,?,?,?)',
                        (tile, layer, meaning['role'], meaning['scaleDenominator'], source.canonical(metadata)))
                    fields = {field['name']: field for field in metadata['dbf']['fields']}
                    for record in native.records(tile, layer, tile_sha256, metadata, components):
                        fid += 1
                        item = native.native_geometry(record['rawShape'])
                        geometry = item['geometry']
                        bounds = item['bounds'] or (None, None, None, None)
                        valid = item['status'] == 'VALID' and not record['deleted']
                        area = geometry.area if valid and geometry.geom_type in ('Polygon', 'MultiPolygon') else None
                        length = geometry.length if valid and geometry.geom_type in ('LineString', 'MultiLineString') else None
                        connection.execute('INSERT INTO features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (fid, tile, layer, record['number'], record['rawShapeSha256'], record['rawDbfSha256'],
                             source.canonical(record['attributes']), int(record['deleted']),
                             shapely.to_wkb(geometry, byte_order=1) if geometry is not None else None,
                             item['status'], item['detail'], source.canonical(item['partMapping']), *bounds, area, length))
                        if item['bounds'] is not None:
                            minx, miny, maxx, maxy = bounds
                            connection.execute('INSERT INTO feature_bounds VALUES(?,?,?,?,?)', (fid, minx, maxx, miny, maxy))
                        counts['records'] += 1
                        counts['deleted'] += record['deleted']
                        counts[item['status']] += 1
                        counts['bboxMismatches'] += item['bboxMatches'] is False
                        layer_counts[layer]['records'] += 1
                        layer_counts[layer][item['status']] += 1
                        if item['detail']:
                            # 오류 좌표가 들어 있는 GEOS 진단은 비공개 카탈로그에만 보존한다.
                            invalid_reasons[layer][item['detail'].split('[')[0]] += 1
                        for field, domain_name in meaning['fieldDomains'].items():
                            raw = record['attributes'].get(field)
                            classified = native.code_meaning(raw, catalog.semantics['domains'][domain_name], meaning['scaleDenominator'])
                            code_counts[layer][field][classified['status']] += 1
                            code_examples[layer][field][raw] += 1
                        for field, raw in record['attributes'].items():
                            if fields[field]['type'] not in ('N', 'F'):
                                continue
                            number, status = native.numeric_value(raw)
                            numeric_counts[layer][field][status] += 1
                            if number is not None:
                                old = numeric_ranges[layer].get(field)
                                numeric_ranges[layer][field] = (min(number, old[0]), max(number, old[1])) if old else (number, number)
                    layer_counts[layer]['layerInstances'] += 1
                if progress and (processed % 100 == 0 or processed == len(tiles)):
                    progress(processed, len(tiles), fid)
            connection.commit()
            connection.execute('CREATE INDEX feature_status ON features(geometry_status)')
            connection.execute('CREATE INDEX layer_role ON layers(role,scale_denominator)')
            # 거의 모든 도형이 정상인 자료에서 상태 인덱스를 과소평가하지 않게 한다.
            connection.execute('ANALYZE')
            connection.execute('VACUUM')
            if connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise source.TopographyDataError('공간 카탈로그 무결성 검사 실패')
            if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise source.TopographyDataError('공간 카탈로그 원본 참조 오류')
        schema_report = {layer: list(variants.values()) for layer, variants in sorted(schemas.items())}
        code_report = {layer: {field: dict(sorted(states.items())) for field, states in sorted(fields.items())}
                       for layer, fields in sorted(code_counts.items())}
        ranges = {layer: {field: {'minimumRawNumeric': str(values[0]), 'maximumRawNumeric': str(values[1]),
                                 'unit': 'NOT_CONFIRMED_BY_CODE_MANUAL'} for field, values in sorted(fields.items())}
                  for layer, fields in sorted(numeric_ranges.items())}
        catalog.verify_snapshot()
        if any(file_sha256(path) != code_hashes[key] for key, path in code_files.items()):
            raise source.TopographyDataError('정규화 중 생성 코드 변경')
        report = {'schemaVersion': 1, 'status': 'NATIVE_GEOMETRY_CATALOG_NOT_SERVICE_MIGRATED',
            'sourceCatalogSha256': catalog.summary['catalogSha256'],
            'sourceManifestSha256': catalog.summary['manifestSha256'],
            'semanticsSha256': catalog.semantics_sha256,
            **code_hashes,
            'spatialSha256': file_sha256(output / 'spatial.sqlite'), 'spatialBytes': (output / 'spatial.sqlite').stat().st_size,
            'coordinateSystem': 'EPSG:5186', 'coordinateOrder': 'x=easting,y=northing',
            'counts': dict(sorted(counts.items())),
            'layerCounts': {k: dict(sorted(v.items())) for k, v in sorted(layer_counts.items())},
            'codeStatusCounts': code_report, 'numericRanges': ranges,
            'numericStatusCounts': {layer: {field: dict(sorted(states.items())) for field, states in sorted(fields.items())}
                                    for layer, fields in sorted(numeric_counts.items())},
            'invalidReasonCounts': {layer: dict(sorted(values.items())) for layer, values in sorted(invalid_reasons.items())},
            'schemaComparisons': schema_report,
            'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string, 'sqlite': sqlite3.sqlite_version},
            'policy': {'geometryRepair': False, 'sourceVertexOrderPreserved': True, 'sourcePartMappingRetained': True,
                'originalCoordinatePrecisionPreserved': True, 'invalidExcludedFromCalculations': True,
                'ufidAssetMerging': False, 'crossScaleMerging': False,
                'seoulCoverageVerified': False, 'tileSeamsVerified': False, 'serviceMigrated': False,
                'verticalDatum': None, 'terrainInterpolation': False}}
        with (output / 'code-values.json').open('x', encoding='utf-8') as stream:
            stream.write(source.canonical({layer: {field: sorted(values.items(), key=lambda item: (item[0] is not None, item[0] or ''))
                for field, values in fields.items()} for layer, fields in code_examples.items()}) + '\n')
        with (output / 'summary.json').open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(report) + '\n')
        return report
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=source.ROOT / source.OUTPUT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        expected = native.read_json(SOURCE_SUMMARY)
        catalog = native.SourceCatalog(args.source, expected)
        report = build(catalog, args.output.absolute(), progress=lambda done, total, count:
            print(f'도엽 {done}/{total} · 원 레코드 {count}', flush=True))
    except source.TopographyDataError as exc:
        parser.exit(1, f'공간 카탈로그 검증 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile, zlib.error,
            sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '공간 카탈로그 검증 실패: 원본·도형·입력 카탈로그 확인 필요\n')
    print(source.canonical({'status': report['status'], 'counts': report['counts'], 'spatialSha256': report['spatialSha256']}))


if __name__ == '__main__':
    main()
