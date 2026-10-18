"""공개 원본의 연결·외부 파일 차단·비개입 실행 확인."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from waterleague_sim.engine import network
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.published_network import digest, execution_input, inspect_input, load_archive, records

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'data/manifests/mendeley-seocho-network-v3.json'
ARCHIVE = ROOT / 'data/raw/mendeley-seocho-v3/dataset.zip'
MINIMAL = b'''[OPTIONS]\nFLOW_UNITS CMS\nFLOW_ROUTING DYNWAVE\n[JUNCTIONS]\nJ 10 3 0 0 0\n[OUTFALLS]\nO 9 FREE NO\n[CONDUITS]\nC J O 20 0.014 0 0\n[XSECTIONS]\nC RECT_CLOSED 2 2 0 0 1\n[COORDINATES]\nJ 200001 400001\nO 200002 400002\n[SUBCATCHMENTS]\nS RG J 1 60 100 2 NaN\n'''


class PublishedNetworkTests(unittest.TestCase):
    def test_topology_and_unknown_crs_are_not_repaired(self):
        audit = inspect_input(MINIMAL)
        self.assertIsNone(audit['horizontalCrs'])
        self.assertIsNone(audit['verticalDatum'])
        self.assertFalse(audit['rankingEligible'])
        self.assertEqual(audit['nonfiniteTokens'][0]['value'], 'NaN')
        self.assertEqual(audit['topology']['nodesWithoutDirectedOutfallPath'], [])
        broken = MINIMAL.replace(b'C J O 20', b'C J UNKNOWN 20')
        self.assertEqual(inspect_input(broken)['topology']['missingReferences'][0]['id'], 'UNKNOWN')
        with self.assertRaisesRegex(FloodModelError, 'DEPENDENCY_UNRESOLVED'):
            execution_input(broken)
        with self.assertRaisesRegex(FloodModelError, 'IDENTIFIER_DUPLICATED'):
            inspect_input(MINIMAL + b'[JUNCTIONS]\nj 11 3 0 0 0\n')

    def test_only_detail_report_token_changes_and_external_input_is_rejected(self):
        raw = MINIMAL + b'[LID_USAGE]\nS PP 1 10 1 0 0 0 "../../report file.txt" * 0 ; keep\r\n'
        prepared, changes = execution_input(raw)
        self.assertEqual(prepared.encode(), raw.replace(b'"../../report file.txt"', b'*'))
        self.assertEqual(len(changes['changes']), 1)
        self.assertFalse(changes['physicsValuesChanged'])
        self.assertEqual(changes['originalSha256'], digest(raw))
        self.assertEqual(changes['executionSha256'], digest(prepared.encode()))
        for external in [b'[TIMESERIES]\nR FILE "../rain.dat"\n', b'[FILES]\nUSE HOTSTART "input"\n',
                         b'[TEMPERATURE]\nFILE "input"\n', b'[POLLUTANTS]\nP MG/L 0 0 0 0\n']:
            with self.assertRaises(FloodModelError):
                execution_input(MINIMAL + external)
        for token in [b'NaN', b'Infinity', b'1e999']:
            with self.assertRaises(FloodModelError):
                execution_input(MINIMAL.replace(b'100 2 NaN', b'100 ' + token + b' NaN'))

    def test_archive_paths_duplicates_and_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / 'source.zip'
            def manifest(member):
                with ZipFile(archive, 'w') as z:
                    z.writestr(member, MINIMAL)
                data = {'schemaVersion': 1, 'rankingEligible': False,
                    'archive': {'file': 'source.zip', 'sha256': digest(archive.read_bytes())},
                    'members': [{'member': member, 'bytes': len(MINIMAL), 'sha256': digest(MINIMAL)}]}
                (root / 'manifest.json').write_text(json.dumps(data))
                return data
            for name in ('../escape.inp', '/absolute.inp', 'folder\\escape.inp'):
                manifest(name)
                with self.assertRaisesRegex(FloodModelError, 'MEMBER_UNSAFE'):
                    load_archive(root, root / 'manifest.json')
            original = manifest('safe.inp')
            self.assertEqual(len(load_archive(root, root / 'manifest.json')[2]), 1)
            original['members'][0]['sha256'] = '0' * 64
            (root / 'manifest.json').write_text(json.dumps(original))
            with self.assertRaisesRegex(FloodModelError, 'MEMBER_HASH'):
                load_archive(root, root / 'manifest.json')
            original = manifest('safe.inp')
            original['members'].append(original['members'][0])
            (root / 'manifest.json').write_text(json.dumps(original))
            with self.assertRaisesRegex(FloodModelError, 'MANIFEST_DUPLICATE'):
                load_archive(root, root / 'manifest.json')


@unittest.skipUnless(ARCHIVE.exists() and network.library_path().exists(), '공개 원본과 고정 EPA 빌드 필요')
class PublishedNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.inputs = load_archive(ROOT, MANIFEST)

    def test_all_published_inputs_preserve_physics_tokens(self):
        self.assertEqual(len(self.inputs), 9)
        for row in self.inputs:
            raw = row['raw']
            prepared, changes = execution_input(raw)
            original_sections = records(raw)[1]
            prepared_sections = records(prepared.encode())[1]
            for section, source_rows in original_sections.items():
                for before, after in zip(source_rows, prepared_sections[section], strict=True):
                    wanted = before['tokens'][:]
                    if section == 'LID_USAGE' and len(wanted) >= 9:
                        wanted[8] = '*'
                    self.assertEqual(wanted, after['tokens'])
            self.assertEqual(row['audit']['topology']['missingReferences'], [])
            self.assertEqual(row['audit']['topology']['nodesWithoutDirectedOutfallPath'], [])

    def test_published_baseline_and_lid_match_unmodified_stock_outputs(self):
        baseline = next(r for r in self.inputs if '/Baseline/' in r['member'])
        lid = next(r for r in self.inputs if r['member'].endswith('/seocho2_baseline LID.inp'))
        for row in (baseline, lid):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                prepared, changes = execution_input(row['raw'])
                (root / 'original.inp').write_bytes(row['raw'])
                # 원 LID 출력도 임시 디렉터리 안에서만 생성하며 출처 파일을 덮어쓰지 않는다.
                subprocess.run([str(network.library_path().parent / 'runswmm'), 'original.inp',
                                'stock.rpt', 'stock.out'], cwd=root, check=True,
                               capture_output=True, timeout=30)
                with EngineProcess('network', prepared, root / 'observed', native_duration=True) as process:
                    result = process.call('run', 300)['result']
                self.assertEqual(digest((root / 'stock.out').read_bytes()),
                                 digest((root / 'observed/network.out').read_bytes()))
                self.assertTrue(result['complete'])
                self.assertEqual(result['timeWindowPolicy'], 'NATIVE_DURATION_DIAGNOSTIC')
                self.assertEqual(result['calendarShortfallSeconds'], 1)
                self.assertEqual(result['numericalStatus'], 'FAILED')
                self.assertGreater(result['convergence']['nonConvergedSteps'], 0)
                self.assertFalse(changes['rankingEligible'])
                for name, expected in result['files'].items():
                    self.assertEqual(digest((root / 'observed' / name).read_bytes()), expected)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(FloodModelError, 'END_TRUNCATED'):
                with EngineProcess('network', baseline['raw'].decode(), Path(temporary) / 'strict'):
                    pass


if __name__ == '__main__':
    unittest.main()
