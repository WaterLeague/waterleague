"""웹 전용 배포의 실행 동일성·비밀 변경 감지와 실패 시 전체 배포 검증."""
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('runtime_identity', Path(__file__).parents[1]/'runtime_identity.py')
identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity)


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        (self.base/'state/secrets').mkdir(parents=True)
        self.prior, self.release = self.base/'previous', self.base/'next'
        self.old = {name: f'ghcr.io/waterleague/waterleague-{name}@sha256:'+str(index)*64
                    for index, name in enumerate(('api', 'worker', 'web'), 1)}
        self.new = {name: f'ghcr.io/waterleague/waterleague-{name}@sha256:'+str(index)*64
                    for index, name in enumerate(('api', 'worker', 'web'), 4)}
        for directory in (self.prior, self.release):
            directory.mkdir()
            (directory/'compose.yml').write_text('name: waterleague\n')
            (directory/'compose.public.yml').write_text('services: {}\n')
        (self.prior/'release.env').write_text(''.join(
            'WL_'+name.upper()+'_IMAGE='+value+'\n' for name, value in self.old.items()))
        self.values = {'ADMIN_USERNAME': 'operator', 'ADMIN_PASSWORD': 'fixture-admin-password',
                       'KMA_API_KEY': 'fixture-observation-secret'}
        self.metadata = {}
        for images, revision in ((self.old, 'old'), (self.new, 'new')):
            for name, reference in images.items():
                self.metadata[reference] = {'Architecture': 'arm64', 'Os': 'linux',
                    'RootFS': {'Type': 'layers', 'Layers': [name+'-filesystem']},
                    'Config': {'User': '10001', 'Env': ['PROFILE=production'],
                               'Labels': {'revision': revision}}}

    def remember(self):
        identity.remember(self.base, self.prior, self.old, self.values, self.metadata.__getitem__)

    def matches(self):
        return identity.matches(self.base, self.prior, self.release, self.new,
                                self.values, self.metadata.__getitem__)

    def test_first_deployment_requires_full_backup_without_inspecting_images(self):
        self.assertFalse(self.matches())

    def test_revision_labels_and_web_filesystem_change_allow_web_only(self):
        self.remember()
        self.metadata[self.new['web']]['RootFS']['Layers'] = ['changed-web']
        self.assertTrue(self.matches())
        for path in (self.base/'state/secrets').iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(self.values['ADMIN_PASSWORD'].encode(), path.read_bytes())

    def test_secret_change_requires_full_backup(self):
        self.remember()
        self.values['ADMIN_PASSWORD'] = 'changed-admin-password'
        self.assertFalse(self.matches())

    def test_server_filesystem_or_execution_configuration_change_requires_full_backup(self):
        for category in ('RootFS', 'Config', 'Architecture'):
            with self.subTest(category=category):
                self.remember()
                original = copy.deepcopy(self.metadata[self.new['api']])
                self.metadata[self.new['api']][category] = {'changed': True}
                self.assertFalse(self.matches())
                self.metadata[self.new['api']] = original

    def test_compose_change_requires_full_backup(self):
        self.remember()
        (self.release/'compose.public.yml').write_text('changed mount\n')
        self.assertFalse(self.matches())

    def test_stale_stamp_does_not_authorize_different_current_server(self):
        identity.remember(self.base, self.release, self.new, self.values, self.metadata.__getitem__)
        self.metadata[self.old['worker']]['RootFS']['Layers'] = ['different-current-filesystem']
        self.assertFalse(self.matches())

    def test_corrupt_stamp_is_full_deploy_and_linked_identity_is_rejected(self):
        self.remember()
        key, stamp = identity.paths(self.base)
        stamp.write_text('incomplete')
        self.assertFalse(self.matches())
        stamp.unlink()
        stamp.symlink_to(key)
        with self.assertRaises(ValueError):
            self.matches()


if __name__ == '__main__':
    unittest.main()
