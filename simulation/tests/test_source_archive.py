"""관측 원문의 중복 보관 방지와 변경·링크 차단 검사."""
import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from waterleague_sim.ingestion import source_archive as archive


class SourceArchiveTests(unittest.TestCase):
    def test_same_source_shares_bytes_without_changing_job_inputs(self):
        raw=b'PUBLIC_OBSERVATION_TEST_ONLY\n';sha=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();a=root/'first.txt';b=root/'second.txt'
            archive.store(root,a,raw,sha);archive.store(root,b,raw,sha)
            self.assertEqual(a.read_bytes(),raw)
            self.assertEqual(a.stat().st_ino,b.stat().st_ino)
            self.assertEqual(len(list((root/'observation-sources').iterdir())),1)
            a.unlink();self.assertEqual(b.read_bytes(),raw)
            self.assertEqual(b.stat().st_mode & 0o222,0)

    def test_corruption_symlink_and_different_target_never_silently_replace_input(self):
        raw=b'PUBLIC_OBSERVATION_TEST_ONLY\n';sha=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();source=root/'original.txt';source.write_bytes(raw)
            bad=root/'link.txt';bad.symlink_to(source)
            with self.assertRaisesRegex(ValueError,'PREVIOUS_SOURCE_INVALID'):
                archive.link(bad,root/'copy.txt',sha)
            target=root/'target.txt';target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'ARCHIVE_CONFLICT'):
                archive.link(source,target,sha)
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH_INVALID'):
                archive.store(root,root/'wrong.txt',raw,'a'*64)
            archive.store(root,root/'valid.txt',raw,sha)
            pool=root/'observation-sources'/(sha+'.txt');pool.chmod(0o600);pool.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'PREVIOUS_SOURCE_INVALID'):
                archive.store(root,root/'later.txt',raw,sha)

    def test_unsupported_link_falls_back_to_verified_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();a=root/'first.txt';b=root/'second.txt';raw=b'PUBLIC_TEST_ONLY'
            a.write_bytes(raw)
            with patch.object(archive.os,'link',side_effect=OSError(errno.EXDEV,'test')):
                archive.link(a,b,hashlib.sha256(raw).hexdigest())
            self.assertEqual(b.read_bytes(),raw)
            self.assertNotEqual(a.stat().st_ino,b.stat().st_ino)
            with patch.object(archive.os,'link',side_effect=OSError(errno.EOPNOTSUPP,'test')):
                archive.store(root,root/'stored.txt',raw,hashlib.sha256(raw).hexdigest())
            self.assertEqual((root/'stored.txt').read_bytes(),raw)
