"""실제 마이그레이션과 배포 권한 목록의 누락 감지."""
from pathlib import Path
import re
import unittest

from deploy.database import TABLES
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class DeploymentContractTests(unittest.TestCase):
    def test_policy_mismatch_stops_before_registry_or_image_build(self):
        import subprocess
        from deploy import ci
        with patch.object(ci, 'run', side_effect=subprocess.CalledProcessError(1, 'policy')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                ci.build()
            run.assert_called_once_with(ci.sys.executable, 'scripts/build_score_policy.py', '--check')

    def test_permission_catalog_covers_all_migrated_tables(self):
        sources = [*ROOT.glob('backend/src/main/resources/db/migration/*.sql'),
                   *ROOT.glob('backend/src/main/java/db/migration/*.java')]
        created = set()
        for path in sources:
            created.update(name.lower() for name in
                           re.findall(r'CREATE TABLE\s+([A-Za-z_]+)', path.read_text()))
        self.assertEqual(created, set(TABLES))
        self.assertEqual(len(TABLES), len(set(TABLES)))
