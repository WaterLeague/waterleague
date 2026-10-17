"""복원 산출물의 경로 격리·손상 감지·연구 계보 연결 검사."""
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import verify_database_restore as restore


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class GenerationDatabase:
    def __init__(self):
        raw = (restore.ROOT / 'simulation/tests/fixtures/pattern-search-v1.json').read_text()
        value = restore.decoded(raw)
        settings = value['settings']
        self.search = [uuid.uuid4(), value['modelHash'], settings['budgetKrw'], settings['seed'],
                       settings['topK'], settings['candidatesPerArm'], raw,
                       hashlib.sha256(raw.encode()).hexdigest()]
        self.sources = []
        for item in value['sources']:
            s = item['sample']
            result = json.dumps({'baseline': {'accountedDischargeM3': 100},
                                 'strategy': {'accountedDischargeM3': float(100-s['score'])},
                                 'score': float(s['score'])})
            self.sources.append([uuid.UUID(s['jobId']), uuid.UUID(s['versionId']), value['modelHash'],
                s['inputHash'], 'SUCCEEDED', result, s['placementsSource'], s['costKrw'], 'KRW'])
        self.candidates = [[c['arm'], c['ordinal'], c['placementsSource'], value['modelHash'],
                            c['inputHash'], c['costKrw']] for c in value['candidates']]

    def execute(self, query, args=None):
        if 'from research_searches' in query:
            return Rows([self.search])
        if 'from research_search_sources' in query:
            return Rows(self.sources)
        if 'from research_candidates' in query:
            return Rows(self.candidates)
        raise AssertionError('예상하지 않은 조회')


class DatabaseRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.destination = Path(self.temp.name) / 'copy'
        self.job, self.token = uuid.uuid4(), uuid.uuid4()
        self.folder = self.root / 'research-candidates' / str(self.job) / str(self.token)
        self.folder.mkdir(parents=True)
        model = json.dumps({'unitCosts': {'RAIN_GARDEN': 10}, 'currency': 'KRW'}).encode()
        self.model_hash = hashlib.sha256(model).hexdigest()
        self.placements = '[{"cellId":"G1","facilityType":"RAIN_GARDEN","areaM2":2}]'
        self.input_hash = hashlib.sha256((self.model_hash+'\n'+self.placements).encode()).hexdigest()
        self.result = {'baseline': {'accountedDischargeM3': 100},
                       'strategy': {'accountedDischargeM3': 90}, 'score': 10}
        for name in restore.FILES:
            (self.folder / name).write_bytes(b'fixture-only-not-swmm')
        (self.folder / 'model-source.json').write_bytes(model)
        (self.folder / 'placements.json').write_text(self.placements)
        (self.folder / 'request.json').write_text(json.dumps({'modelHash': self.model_hash,
            'inputHash': self.input_hash, 'placements': json.loads(self.placements)}))
        (self.folder / 'result.json').write_text(json.dumps(self.result))
        self.manifest()

    def manifest(self):
        (self.folder / 'manifest.json').write_text(json.dumps({
            name: restore.digest(self.folder / name) for name in restore.FILES}))

    def check(self, root=None, copy_to=None, kind='RESEARCH_CANDIDATE', result=None, cost=20):
        stored = (self.result if result is None else result) | {'artifactToken': str(self.token),
                  'modelHash': self.model_hash, 'inputHash': self.input_hash}
        return restore.check_one_artifact(root or self.root, kind, self.job, self.model_hash,
            self.input_hash, json.dumps(stored), self.placements, Decimal(cost), 'KRW', copy_to)

    def test_copied_candidate_files_validate_without_source_files(self):
        first = self.check(copy_to=self.destination)
        self.root.rename(self.root.with_name('unavailable'))
        self.assertEqual(first, self.check(root=self.destination))
        copied = self.destination / 'research-candidates' / str(self.job) / str(self.token)
        self.assertEqual(len(list(copied.iterdir())), 19)
        with self.assertRaises(FileNotFoundError):
            (self.root / 'research-candidates').iterdir().__next__()

    def test_wrong_queue_and_duplicate_destination_are_rejected(self):
        with self.assertRaises(restore.RestoreCheckError):
            self.check(kind='PERSONAL')
        self.check(copy_to=self.destination)
        with self.assertRaises(FileExistsError):
            self.check(copy_to=self.destination)

    def test_missing_modified_and_symbolic_files_are_rejected(self):
        path = self.folder / 'baseline.out'
        original = path.read_bytes()
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(restore.RestoreCheckError, 'hash'):
            self.check()
        path.unlink()
        with self.assertRaises(restore.RestoreCheckError):
            self.check()
        other = Path(self.temp.name) / 'outside'
        other.write_bytes(original)
        path.symlink_to(other)
        with self.assertRaisesRegex(restore.RestoreCheckError, '링크'):
            self.check()

    def test_research_namespace_and_root_symlinks_are_rejected(self):
        namespace = self.root / 'research-candidates'
        moved = self.root / 'moved'
        namespace.rename(moved)
        namespace.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(restore.RestoreCheckError, '링크'):
            self.check()
        alias = self.root.with_name('alias')
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(restore.RestoreCheckError, '링크'):
            self.check(root=alias)

    def test_rehashed_request_or_result_and_bad_cost_are_rejected(self):
        with self.assertRaisesRegex(restore.RestoreCheckError, '비용'):
            self.check(cost=21)
        request = self.folder / 'request.json'
        original = request.read_text()
        request.write_text(original.replace(self.input_hash, '0'*64))
        self.manifest()
        with self.assertRaisesRegex(restore.RestoreCheckError, '요청'):
            self.check()
        request.write_text(original)
        changed = self.result | {'score': 11}
        (self.folder / 'result.json').write_text(json.dumps(changed))
        self.manifest()
        with self.assertRaisesRegex(restore.RestoreCheckError, '점수'):
            self.check(result=changed)

    def test_ambiguous_json_and_copy_corruption_are_rejected(self):
        request = self.folder / 'request.json'
        original = request.read_bytes()
        for raw in [b'{"placements":[],"placements":[]}', b'{"score":NaN}']:
            request.write_bytes(raw)
            self.manifest()
            with self.assertRaises(ValueError):
                self.check()
        request.write_bytes(original)
        self.manifest()
        with patch.object(restore.shutil, 'copyfileobj', side_effect=lambda src, dst: dst.write(b'bad')):
            with self.assertRaisesRegex(restore.RestoreCheckError, '사본 hash'):
                self.check(copy_to=self.destination)

    def test_generation_replays_and_matches_all_database_records(self):
        database = GenerationDatabase()
        report = restore.check_generation(database)
        self.assertEqual((report['searches'], report['candidates']), (1, 8))
        self.assertEqual(report, restore.check_generation(database))

    def test_generation_rejects_source_candidate_settings_or_hash_divergence(self):
        mutations = [lambda d: d.search.__setitem__(7, '0'*64),
                     lambda d: d.search.__setitem__(3, 99),
                     lambda d: d.sources.pop(),
                     lambda d: d.sources[0].__setitem__(1, uuid.uuid4()),
                     lambda d: d.sources[0].__setitem__(4, 'FAILED'),
                     lambda d: d.sources[0].__setitem__(7, Decimal(0)),
                     lambda d: d.candidates.pop(),
                     lambda d: d.candidates[0].__setitem__(0, 'INVALID'),
                     lambda d: d.candidates[0].__setitem__(2, '[]'),
                     lambda d: d.candidates[0].__setitem__(5, Decimal(0))]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                database = GenerationDatabase()
                mutate(database)
                with self.assertRaises((restore.RestoreCheckError, ValueError)):
                    restore.check_generation(database)


if __name__ == '__main__':
    unittest.main()
