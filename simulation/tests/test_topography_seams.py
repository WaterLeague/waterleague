import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

import shapely
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_topography_seams as audit
import prepare_seoul_topography as source


class TopographySeamsTests(unittest.TestCase):
    def pair(self):
        first = {'fid': 1, 'tile': '377052201', 'attributes': {'층수': '3'}, 'geometry': box(8, 2, 10, 8)}
        second = {'fid': 2, 'tile': '377052202', 'attributes': {'층수': '3'}, 'geometry': box(10, 2, 12, 8)}
        frames = {'377052201': {'geometry': box(0, 0, 10, 10), 'scale': 1000, 'codeMatches': True},
                  '377052202': {'geometry': box(10, 0, 20, 10), 'scale': 1000, 'codeMatches': True}}
        return first, second, frames

    def test_fragment_join_evidence_requires_attributes_disjoint_area_and_both_original_edges(self):
        first, second, frames = self.pair()
        self.assertEqual(audit.compare_pair(first, second, frames), 'VERIFIED_DISJOINT_FRAGMENT_EDGE')
        frames['377052202']['geometry'] = box(9, 0, 20, 10)
        self.assertEqual(audit.compare_pair(first, second, frames), 'NOT_ON_BOTH_ORIGINAL_FRAME_EDGES')
        second['attributes'] = {'층수': '4'}
        self.assertEqual(audit.compare_pair(first, second, frames), 'ATTRIBUTE_CONFLICT')

    def test_no_coordinate_snapping_or_ufid_only_inference(self):
        first, second, frames = self.pair()
        second['geometry'] = box(10.000000001, 2, 12, 8)
        self.assertEqual(audit.compare_pair(first, second, frames), 'NO_SHARED_EDGE')
        second['geometry'] = box(9.999, 2, 12, 8)
        self.assertEqual(audit.compare_pair(first, second, frames), 'POSITIVE_AREA_OVERLAP')
        second['tile'] = first['tile']
        self.assertEqual(audit.compare_pair(first, second, frames), 'SAME_TILE_DIFFERENT_RECORDS')

    def test_exact_coincidence_preserves_attribute_conflict_and_unverified_frames(self):
        first, second, frames = self.pair()
        second['geometry'] = shapely.reverse(first['geometry'])
        self.assertEqual(audit.compare_pair(first, second, frames), 'COINCIDENT_SAME_ATTRIBUTES')
        second['attributes'] = {'층수': None}
        self.assertEqual(audit.compare_pair(first, second, frames), 'COINCIDENT_ATTRIBUTE_CONFLICT')
        first, second, frames = self.pair()
        frames['377052202']['codeMatches'] = False
        self.assertEqual(audit.compare_pair(first, second, frames), 'FRAME_NOT_VERIFIED')

    def test_coverage_reports_missing_sheets_and_uncovered_area_without_filling(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source.sqlite'
            with sqlite3.connect(path) as database:
                database.executescript('''CREATE TABLE tiles(tile TEXT);CREATE TABLE layers(tile TEXT,layer TEXT);
                    CREATE TABLE features(fid INTEGER,tile TEXT,layer TEXT,properties TEXT,geometry_wkb BLOB,
                        geometry_status TEXT,record_number INTEGER);''')
                for index, tile in enumerate(['377052201', '377052202']):
                    geometry = box(index * 10, 0, (index + 1) * 10, 10)
                    database.execute('INSERT INTO tiles VALUES(?)', (tile,))
                    database.execute('INSERT INTO layers VALUES(?,?)', (tile, 'N1A_H0010000'))
                    database.execute('INSERT INTO features VALUES(?,?,?,?,?,?,?)', (index + 1, tile,
                        'N1A_H0010000', json.dumps({'도엽코드': tile}), shapely.to_wkb(geometry), 'VALID', 1))
                database.execute('INSERT INTO tiles VALUES(?)', ('377052203',))
            boundary = box(0, 0, 30, 10)
            value = {'boundary': mapping(boundary), 'districts': [{'id': '11110', 'name': '시험구', 'nativeGeometry': mapping(boundary)}]}
            frames, report = audit.frame_coverage(SimpleNamespace(database=path), value)
            self.assertEqual(len(frames), 2)
            self.assertEqual(report['missingFrameTiles'], ['377052203'])
            self.assertEqual(report['uncoveredM2'], 100)
            self.assertEqual(report['covered1000M2'], 200)
            self.assertEqual(report['districts']['11110']['uncoveredM2'], 100)
            self.assertEqual(boundary.area, 300)


if __name__ == '__main__':
    unittest.main()
