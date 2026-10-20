import copy
import io
import json
from pathlib import Path
import sqlite3
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import pyproj

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_seoul_topography as source

LAYER = 'N1A_B0010000'
TILE = '377052201'


def archive_bytes(members, compression=zipfile.ZIP_DEFLATED):
    target = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(target, 'w', compression=compression) as archive:
            for name, payload in members:
                # 시험 ZIP의 현재 시각이 원문 보존 대조에 섞이지 않게 한다.
                if isinstance(name, str):
                    name = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    name.compress_type = compression
                archive.writestr(name, payload)
    return target.getvalue()


def shape_header(size, bounds=(200000., 550000., 200010., 550010.)):
    return struct.pack('>7I', 9994, 0, 0, 0, 0, 0, size // 2) + struct.pack('<2I8d', 1000, 5, *bounds, 0, 0, 0, 0)


def components(names=('가동', '나동'), identifiers=('same', 'same'), deleted=(False, False)):
    rings = [[(200000., 550000.), (200000., 550010.), (200010., 550010.),
              (200010., 550000.), (200000., 550000.)],
             [(200002., 550002.), (200008., 550002.), (200008., 550008.),
              (200002., 550008.), (200002., 550002.)]]
    content = struct.pack('<I4d2I2I', 5, 200000., 550000., 200010., 550010., 2, 10, 0, 5)
    content += b''.join(struct.pack('<2d', *point) for ring in rings for point in ring)
    count, size = len(names), len(content)
    shp = shape_header(100 + count * (size + 8)) + b''.join(
        struct.pack('>2I', index + 1, size // 2) + content for index in range(count))
    shx = shape_header(100 + count * 8) + b''.join(
        struct.pack('>2I', (100 + index * (size + 8)) // 2, size // 2) for index in range(count))
    fields = [('UFID', 'C', 10), ('명칭', 'C', 20), ('층수', 'N', 4)]
    dbf = bytearray(32)
    dbf[0] = 3
    struct.pack_into('<IHH', dbf, 4, count, 33 + len(fields) * 32, 35)
    for name, kind, width in fields:
        field = bytearray(32)
        encoded = name.encode('cp949')
        field[:len(encoded)] = encoded
        field[11], field[16] = ord(kind), width
        dbf.extend(field)
    dbf.extend(b'\r')
    for name, identifier, removed in zip(names, identifiers, deleted):
        dbf.extend(b'*' if removed else b' ')
        dbf.extend(identifier.encode('cp949').ljust(10))
        dbf.extend(name.encode('cp949').ljust(20))
        dbf.extend(b'    ')
    dbf.extend(b'\x1a')
    return {'shp': shp, 'shx': shx, 'dbf': bytes(dbf), 'prj': pyproj.CRS(5186).to_wkt().encode()}


def tile_bytes(parts=None):
    return archive_bytes([(f'{LAYER}.{extension}', payload) for extension, payload in (parts or components()).items()])


class SeoulTopographyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def manifest(self, tiles_by_district=None):
        if tiles_by_district is None:
            tiles_by_district = {'가구': [(TILE, tile_bytes())], '나구': [(TILE, tile_bytes())]}
        files = []
        for district, tiles in sorted(tiles_by_district.items()):
            payload = archive_bytes([(tile + '.zip', content) for tile, content in tiles])
            name = district + '.zip'
            (self.root / name).write_bytes(payload)
            files.append({'role': 'DISTRICT_TILE_PACKAGE', 'district': district, 'localPath': name,
                          'bytes': len(payload), 'sha256': source.digest(payload), 'tileZipCount': len(tiles)})
        (self.root / 'manual.pdf').write_bytes(b'public reference')
        files.append({'role': 'LAYER_CODE_REFERENCE', 'localPath': 'manual.pdf', 'bytes': 16,
                      'sha256': source.digest(b'public reference')})
        references = sum(len(tiles) for tiles in tiles_by_district.values())
        unique = len({tile for tiles in tiles_by_district.values() for tile, _ in tiles})
        manifest = {'schemaVersion': 1, 'distributionUpdatedAt': '2026-03-07', 'files': files,
                    'inventory': {'tileReferences': references, 'uniqueTileCount': unique,
                                  'repeatedTileReferences': references - unique}}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest, ensure_ascii=False))
        return path, manifest

    def build(self, path, name='output'):
        return source.build(path, self.root / name, root=self.root)

    def test_build_deduplicates_tiles_and_preserves_native_source_and_record_identity(self):
        path, _ = self.manifest()
        summary = self.build(path)
        self.assertEqual(summary['counts']['uniqueTileCount'], 1)
        self.assertEqual(summary['counts']['repeatedTileReferences'], 1)
        self.assertEqual(summary['counts']['rawRecords'], 2)
        self.assertEqual((self.root / 'output/tiles' / (TILE + '.zip')).read_bytes(), tile_bytes())
        with sqlite3.connect(self.root / 'output/catalog.sqlite') as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM tile_sources').fetchone()[0], 2)
            metadata = json.loads(connection.execute('SELECT metadata FROM layers').fetchone()[0])
        self.assertEqual(metadata['dbf']['fields'][1]['name'], '명칭')
        self.assertEqual(metadata['dbf']['fields'][2]['type'], 'N')
        self.assertEqual(metadata['originalWkt'], components()['prj'].decode())
        self.assertEqual(metadata['components']['shp']['sha256'], source.digest(components()['shp']))
        self.assertFalse(metadata['geometryValidityVerified'])
        self.assertFalse(summary['checks']['serviceMigration'])
        checksum = source.digest(tile_bytes())
        self.assertNotEqual(source.record_id(TILE, LAYER, 1, checksum), source.record_id(TILE, LAYER, 2, checksum))
        self.assertNotEqual(source.record_id(TILE, LAYER, 1, checksum), source.record_id(TILE, LAYER, 1, 'a' * 64))

    def test_catalog_and_summary_bytes_are_reproducible_and_output_cannot_be_overwritten(self):
        path, _ = self.manifest()
        self.build(path, 'a')
        self.build(path, 'b')
        for name in ('catalog.sqlite', 'summary.json'):
            self.assertEqual((self.root / 'a' / name).read_bytes(), (self.root / 'b' / name).read_bytes())
        with self.assertRaises(source.TopographyDataError):
            self.build(path, 'a')
        (self.root / 'link').symlink_to(self.root / 'a', target_is_directory=True)
        with self.assertRaises(source.TopographyDataError):
            self.build(path, 'link')

    def test_conflicting_tile_hash_rejects_whole_build_without_completion_marker(self):
        path, _ = self.manifest({'가구': [(TILE, tile_bytes())],
                                '나구': [(TILE, tile_bytes(components(names=('다동', '나동'))))]})
        with self.assertRaisesRegex(source.TopographyDataError, '충돌'):
            self.build(path)
        self.assertFalse((self.root / 'output').exists())

    def test_source_hash_size_manual_and_counts_are_required(self):
        for change in ('hash', 'size', 'manual', 'count'):
            with self.subTest(change=change):
                path, manifest = self.manifest()
                if change == 'hash':
                    manifest['files'][0]['sha256'] = '0' * 64
                elif change == 'size':
                    manifest['files'][0]['bytes'] += 1
                elif change == 'manual':
                    (self.root / 'manual.pdf').write_bytes(b'changed reference')
                else:
                    manifest['inventory']['uniqueTileCount'] += 1
                path.write_text(json.dumps(manifest))
                with self.assertRaises(source.TopographyDataError):
                    self.build(path)
                self.assertFalse((self.root / 'output').exists())

    def test_relative_paths_and_symlinks_are_rejected(self):
        for name in ('../outside.zip', '/outside.zip', 'C:source.zip', 'a\\b.zip', 'a/./b.zip'):
            with self.subTest(name=name), self.assertRaises(source.TopographyDataError):
                source.project_path(self.root, name)
        path, manifest = self.manifest()
        (self.root / 'linked').symlink_to(self.root, target_is_directory=True)
        manifest['files'][0]['localPath'] = 'linked/가구.zip'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(source.TopographyDataError):
            self.build(path)

    def test_archive_traversal_nulls_duplicates_and_special_files_are_rejected(self):
        invalid_sets = [[('../evil', b'x')], [('/evil', b'x')], [('C:evil', b'x')],
            [('a\\evil', b'x')], [('dir/', b'')], [('same', b'1'), ('SAME', b'2')],
            [('é', b'1'), ('e\u0301', b'2')]]
        for members in invalid_sets:
            with self.subTest(members=members), zipfile.ZipFile(io.BytesIO(archive_bytes(members))) as archive:
                with self.assertRaises(source.TopographyDataError):
                    source.archive_members(archive)
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR):
            info = zipfile.ZipInfo('member')
            info.create_system = 3
            info.external_attr = (kind | 0o600) << 16
            with zipfile.ZipFile(io.BytesIO(archive_bytes([(info, b'target')]))) as archive:
                with self.assertRaises(source.TopographyDataError):
                    source.archive_members(archive)
        with zipfile.ZipFile(io.BytesIO(archive_bytes([('safe', b'x')]))) as archive:
            archive.infolist()[0].orig_filename = 'safe\0hidden'
            with self.assertRaises(source.TopographyDataError):
                source.archive_members(archive)

    def test_limits_encryption_and_crc_are_enforced_before_publication(self):
        payload = archive_bytes([('a', b'abc'), ('b', b'abc')], zipfile.ZIP_STORED)
        for constant, limit in [('MAX_ENTRIES', 1), ('MAX_MEMBER_BYTES', 2), ('MAX_ARCHIVE_BYTES', 5)]:
            with self.subTest(constant=constant), patch.object(source, constant, limit):
                with zipfile.ZipFile(io.BytesIO(payload)) as archive, self.assertRaises(source.TopographyDataError):
                    source.archive_members(archive)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            archive.infolist()[0].flag_bits |= 1
            with self.assertRaises(source.TopographyDataError):
                source.archive_members(archive)
        corrupted = payload.replace(b'abc', b'xbc', 1)
        with zipfile.ZipFile(io.BytesIO(corrupted)) as archive:
            with self.assertRaises(zipfile.BadZipFile):
                source.read_member(archive, archive.infolist()[0])

    def test_source_mutation_during_read_is_rejected(self):
        path = self.root / 'mutable'
        path.write_bytes(b'original')
        with self.assertRaisesRegex(source.TopographyDataError, '검사 중'):
            with source.source_stream(path):
                path.write_bytes(b'modified')

    def test_esri_wkt_rounding_is_accepted_but_another_meter_projection_is_rejected(self):
        parts = components()
        parts['prj'] = pyproj.CRS(5186).to_wkt('WKT1_ESRI').encode()
        self.assertEqual(source.inspect_layer(LAYER, parts)['nativeCrs'], 'EPSG:5186')
        parts['prj'] = pyproj.CRS(5181).to_wkt('WKT1_ESRI').encode()
        with self.assertRaises(source.TopographyDataError):
            source.inspect_layer(LAYER, parts)

    def test_layer_component_schema_crs_and_encoding_errors_do_not_pass(self):
        for error in ('missing', 'count', 'offset', 'length', 'crs', 'encoding', 'field', 'kind', 'parts', 'nan'):
            with self.subTest(error=error):
                parts = components()
                if error == 'missing':
                    del parts['shx']
                elif error == 'crs':
                    parts['prj'] = pyproj.CRS(4326).to_wkt().encode()
                elif error == 'encoding':
                    parts['dbf'] = parts['dbf'][:-2] + b'\xff\x1a'
                else:
                    extension, offset, fmt, value = {
                        'count': ('dbf', 4, '<I', 1), 'offset': ('shx', 100, '>I', 1),
                        'length': ('shp', 104, '>I', 1), 'field': ('dbf', 32 + 16, '<B', 11),
                        'kind': ('shp', 108, '<I', 3), 'parts': ('shp', 108 + 44, '<I', 1),
                        'nan': ('shp', 108 + 52, '<d', float('nan'))}[error]
                    changed = bytearray(parts[extension])
                    struct.pack_into(fmt, changed, offset, value)
                    parts[extension] = bytes(changed)
                with self.assertRaises((source.TopographyDataError, UnicodeError)):
                    source.inspect_layer(LAYER, parts)

    def test_original_holes_deleted_rows_blanks_and_unknown_codes_are_preserved(self):
        parts = components(identifiers=('', 'UNKNOWN'), deleted=(False, True))
        before = copy.deepcopy(parts)
        inspected = source.inspect_layer(LAYER, parts)
        self.assertEqual(inspected['dbf']['deletedRecordCount'], 1)
        self.assertEqual(parts, before)
        self.assertEqual(struct.unpack_from('<I', parts['shp'], 108 + 36)[0], 2)
        self.assertFalse(inspected['geometryValidityVerified'])
        self.assertEqual(inspected['encoding'], 'cp949')
        parts['cpg'] = b'EUC-KR'
        self.assertEqual(source.inspect_layer(LAYER, parts)['encoding'], 'cp949')
        parts['cpg'] = b'UTF-8'
        with self.assertRaises(source.TopographyDataError):
            source.inspect_layer(LAYER, parts)

    def test_euc_kr_declaration_mismatch_is_recorded_without_replacing_cp949_text(self):
        parts = components(names=('힣', '가동'))
        parts['cpg'] = b'EUC-KR'
        result = source.inspect_layer(LAYER, parts)
        self.assertEqual(result['declaredCpg'], 'EUC-KR')
        self.assertEqual(result['encoding'], 'cp949')
        self.assertEqual(result['dbf']['encodingDeclarationMismatchRecords'], 1)
        self.assertEqual(result['components']['dbf']['sha256'], source.digest(parts['dbf']))

    def test_inner_unknown_file_missing_component_and_overall_limits_abort_build(self):
        for error in ('unknown', 'missing', 'total', 'tiles'):
            with self.subTest(error=error):
                parts = components()
                if error == 'missing':
                    del parts['prj']
                tile = tile_bytes(parts)
                if error == 'unknown':
                    tile = archive_bytes([('unexpected.xml', b'data')])
                path, _ = self.manifest({'가구': [(TILE, tile)]})
                with patch.object(source, 'MAX_TOTAL_BYTES', 1 if error == 'total' else source.MAX_TOTAL_BYTES):
                    with patch.object(source, 'MAX_TILES', 0 if error == 'tiles' else source.MAX_TILES):
                        with self.assertRaises(source.TopographyDataError):
                            self.build(path)
                self.assertFalse((self.root / 'output').exists())

    def test_published_summary_is_bound_to_current_generator_and_source_manifest(self):
        published = json.loads((source.ROOT / 'data/manifests/seoul-topography-catalog-v1.json').read_text())
        manifest_path = source.ROOT / source.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(published['generatorSha256'], source.digest(Path(source.__file__).read_bytes()))
        self.assertEqual(published['manifestSha256'], source.digest(manifest_path.read_bytes()))
        self.assertEqual(published['packageCount'], manifest['inventory']['packageCount'])
        for key in ('tileReferences', 'uniqueTileCount', 'repeatedTileReferences'):
            self.assertEqual(published['counts'][key], manifest['inventory'][key])
        self.assertEqual(published['layerTypeCount'], len(published['layerTileCounts']))
        self.assertEqual(published['layerInstanceCount'], sum(published['layerTileCounts'].values()))
        for check in ('geometryValidity', 'seoulCoverage', 'fieldAccuracy', 'serviceMigration'):
            self.assertFalse(published['checks'][check])


if __name__ == '__main__':
    unittest.main()
