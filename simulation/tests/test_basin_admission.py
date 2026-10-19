"""공개 경계의 층위·교차 및 설치 당시 재현 정책 보존."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import Polygon
from scripts.prepare_basin_footprints import overlap
from waterleague_sim.admission import archive, ROOT, POLICIES


class BasinAdmissionTests(unittest.TestCase):
    def test_holes_roof_and_touching_edges_do_not_become_ground_overlap(self):
        boundary = Polygon([(0,0),(10,0),(10,10),(0,10)],
                           [[(2,2),(4,2),(4,4),(2,4)]])
        def cell(x, y, kind='GROUND'):
            return {'kind':kind, 'coordinates':[(x,y),(x+1,y),(x+1,y+1),(x,y+1)]}
        self.assertEqual(overlap(cell(0,0), boundary), 1)
        self.assertEqual(overlap(cell(0,0,'ROOF'), boundary), 0)
        self.assertEqual(overlap(cell(2,2), boundary), 0)
        self.assertEqual(overlap(cell(10,0), boundary), 0)
        self.assertEqual(overlap(cell(9.5,0), boundary), .5)

    def test_archives_exact_policy_and_preserves_legacy_absence(self):
        raw = (ROOT/'backend/src/main/resources/infrastructure/seoul-basin-footprints-20261018-v1.json').read_bytes()
        source = json.loads(raw)
        policy = {k:source[k] for k in ('version','sourceSha256','scope','historicalExistenceVerified')}
        policy['sha256'] = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            archive(None, directory)
            self.assertEqual(list(directory.iterdir()), [])
            archive(policy, directory)
            self.assertEqual((directory/'public-asset-policy.json').read_bytes(), raw)
            self.assertEqual(len(source['exclusions']), 86)
            self.assertEqual(len(source['assets']), 3)
            with self.assertRaisesRegex(ValueError, 'INSTALLATION_POLICY_INVALID'):
                archive(policy | {'version':'../../untrusted'}, directory)
            with self.assertRaisesRegex(ValueError, 'INSTALLATION_POLICY_SOURCE_INVALID'):
                archive(policy | {'historicalExistenceVerified':True}, directory)

    def test_current_building_reservation_and_all_previous_policy_bytes(self):
        self.assertIn('seoul-infrastructure-occupancy-20261019-v5', POLICIES)
        for version, digest in POLICIES.items():
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                raw = (ROOT/'backend/src/main/resources/infrastructure'/f'{version}.json').read_bytes()
                source = json.loads(raw)
                policy = {k:source[k] for k in ('version','sourceSha256','scope','historicalExistenceVerified')}
                policy['sha256'] = digest
                archive(policy, Path(temp))
                self.assertEqual((Path(temp)/'public-asset-policy.json').read_bytes(),raw)
                with self.assertRaisesRegex(ValueError,'INSTALLATION_POLICY_INVALID'):
                    archive(policy | {'sha256':'0'*64}, Path(temp))


if __name__ == '__main__':
    unittest.main()
