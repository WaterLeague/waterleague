"""일반 배출 중지 이용조의 초기 저장·비상 배수·재이용 미산정 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.cistern_network import compile_cistern
from waterleague_sim.engine.connected_storage import result_summary
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.cistern_network import source, design


class ClosedCisternTests(unittest.TestCase):
    def test_closed_mode_cannot_silently_accept_missing_or_conflicting_port_inputs(self):
        raw = source()
        original = design(raw)
        for drain in (None, {}, False, {'mode': 'CLOSED'}, {'mode': 'CLOSED_NO_WITHDRAWAL', **original['drain']}):
            with self.subTest(drain=drain), self.assertRaisesRegex(FloodModelError, 'PORT_INVALID'):
                compile_cistern(raw, original | {'drain': drain})
        changed = deepcopy(original)
        changed['drain'] = {'mode': 'CLOSED_NO_WITHDRAWAL'}
        changed['overflow']['crestM'] = 2
        with self.assertRaisesRegex(FloodModelError, 'PORT_ELEVATION_INVALID'):
            compile_cistern(raw, changed)

    def test_storage_is_retained_until_emergency_port_and_never_counted_as_reuse(self):
        cases = [('dry', 0, .8, True), ('empty', 0, 0, True), ('wet', 600, 1.2, True),
                 ('full', 0, 1.4, True), ('gravity', 0, .8, False), ('dry-replay', 0, .8, True)]
        ledgers = {}
        with tempfile.TemporaryDirectory(prefix='wl-closed-cistern-') as directory:
            for name, rain, initial, closed in cases:
                with self.subTest(name=name):
                    raw = source(backwater=True).replace(b'00:00 3600', f'00:00 {rain}'.encode())
                    spec = design(raw) | {'initialDepthM': initial}
                    if closed:
                        spec['drain'] = {'mode': 'CLOSED_NO_WITHDRAWAL'}
                    derived, metadata = compile_cistern(raw, spec)
                    ports = [r['tokens'][0] for r in records(derived)[1]['ORIFICES']]
                    self.assertEqual('WLCT_Cistern_D' in ports, not closed)
                    self.assertIn('WLCT_Cistern_O', ports)
                    target = Path(directory) / name
                    with EngineProcess('network', derived.decode(), target, native_duration=True) as process:
                        result = process.call('run', 1)['result']
                    self.assertEqual(result['numericalStatus'], 'PASSED', result['numericalQuality'])
                    summary = result_summary(metadata, result['initial'], result['final'])
                    self.assertEqual(summary['numericalStatus'], 'PASSED', summary)
                    ledger = ledgers[name] = summary['wholeRunLedger']['facilities'][0]
                    self.assertEqual(ledger['drainOperation'],
                                     'CLOSED_NO_WITHDRAWAL' if closed else 'GRAVITY_ORIFICE')
                    self.assertIsNone(ledger['reuseM3'])
                    self.assertEqual(ledger['reuseStatus'], 'NOT_CALCULATED_NO_USE_DEMAND')
                    self.assertEqual(ledger['floodingM3'], 0)
                    if closed:
                        frames = [json.loads(line) for line in (target/'network-frames.jsonl').read_text().splitlines()]
                        self.assertTrue(all('WLCT_Cistern_D' not in f['links'] for f in frames))
                    if name in ('dry', 'empty', 'dry-replay'):
                        self.assertAlmostEqual(ledger['initialStorageM3'], ledger['finalStorageM3'], delta=1e-8)
                        self.assertEqual(ledger['outflowIncludingFloodingM3'], 0)
            self.assertEqual(ledgers['dry'], ledgers['dry-replay'])
            self.assertGreater(ledgers['dry']['finalStorageM3'], ledgers['gravity']['finalStorageM3'])
            self.assertGreater(ledgers['wet']['inflowM3'], 0)
            for name in ('wet', 'full'):
                self.assertGreater(ledgers[name]['outflowIncludingFloodingM3'], 0)
                self.assertGreater(ledgers[name]['finalStorageM3'], 0)


if __name__ == '__main__':
    unittest.main()
