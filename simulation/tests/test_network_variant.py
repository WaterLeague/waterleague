"""수치 파생 입력의 수리 제원·평가 창 불변 검사."""
from pathlib import Path
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.ingestion.network_variant import derive, hydraulic_input_hash
from waterleague_sim.ingestion.published_network import digest, load_archive, records

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = b'''[OPTIONS] ; source\r\nFLOW_UNITS CMS\r\nFLOW_ROUTING DYNWAVE\r\nMAX_TRIALS   8 ; retained\r\nHEAD_TOLERANCE 0.0015\r\n[JUNCTIONS]\r\nJ 10 3 0 0 0\r\n[OUTFALLS]\r\nO 9 FREE NO\r\n[CONDUITS]\r\nC J O 20 0.014 0 0\r\n[XSECTIONS]\r\nC RECT_CLOSED 2 2 0 0 1\r\n[COORDINATES]\r\nJ 200001 400001\r\nO 200002 400002\r\n'''
PROFILE = {'id': 'slot-fine', 'options': {'SURCHARGE_METHOD': 'SLOT', 'ROUTING_STEP': .0625,
                                        'MINIMUM_STEP': .025, 'MAX_TRIALS': 200}}


class NetworkVariantTests(unittest.TestCase):
    def test_original_input_and_all_physical_tokens_remain_unchanged(self):
        before = digest(MINIMAL)
        raw, metadata = derive(MINIMAL, PROFILE)
        self.assertEqual(digest(MINIMAL), before)
        self.assertEqual(metadata['originalSha256'], before)
        self.assertEqual(metadata['derivedSha256'], digest(raw))
        self.assertEqual(hydraulic_input_hash(MINIMAL), hydraulic_input_hash(raw))
        self.assertIn(b'MAX_TRIALS   200 ; retained\r\n', raw)
        self.assertIn(b'HEAD_TOLERANCE 0.0015\r\n', raw)
        self.assertEqual(metadata['originalSurchargeMethod'], 'EXTRAN')
        self.assertTrue(metadata['hydraulicApproximationChanged'])
        self.assertFalse(metadata['rankingEligible'])
        self.assertFalse(metadata['historicalReconstructionEligible'])
        self.assertEqual(derive(MINIMAL, PROFILE), (raw, metadata))

    def test_relaxed_tolerance_and_physical_changes_cannot_be_hidden_as_numerics(self):
        for key in ('HEAD_TOLERANCE', 'MIN_SURFAREA', 'START_DATE', 'END_DATE', 'INFILTRATION', 'ALLOW_PONDING'):
            with self.assertRaisesRegex(FloodModelError, 'OPTION_REJECTED'):
                derive(MINIMAL, {'id': 'invalid', 'options': {key: 1}})
        for raw in (MINIMAL.replace(b'20 0.014', b'25 0.014'),
                    MINIMAL.replace(b'HEAD_TOLERANCE 0.0015', b'HEAD_TOLERANCE 0.015')):
            self.assertNotEqual(hydraulic_input_hash(raw), hydraulic_input_hash(MINIMAL))
        for options in ({'ROUTING_STEP': float('nan')}, {'MINIMUM_STEP': True},
                        {'MAX_TRIALS': 1e10}, {'SURCHARGE_METHOD': 'SLOT\nALLOW_PONDING YES'},
                        {'ROUTING_STEP': .1, 'MINIMUM_STEP': .2}):
            with self.assertRaises(FloodModelError):
                derive(MINIMAL, {'id': 'invalid', 'options': options})

    @unittest.skipUnless((ROOT / 'data/raw/mendeley-seocho-v3/dataset.zip').exists(), '보관 공개 원본 필요')
    def test_all_nine_source_designs_keep_hydraulic_records_and_time_options(self):
        _, _, inputs = load_archive(ROOT, ROOT / 'data/manifests/mendeley-seocho-network-v3.json')
        for row in inputs:
            raw, metadata = derive(row['raw'], PROFILE)
            before, after = records(row['raw'])[1], records(raw)[1]
            for section in ('JUNCTIONS', 'OUTFALLS', 'CONDUITS', 'XSECTIONS', 'INFLOWS', 'TIMESERIES', 'SUBCATCHMENTS'):
                self.assertEqual(before[section], [{**original, 'line': old['line']}
                    for old, original in zip(before[section], after[section], strict=True)])
            wanted = {r['tokens'][0]: r['tokens'][1:] for r in before['OPTIONS']
                      if r['tokens'][0].endswith(('_DATE', '_TIME'))}
            actual = {r['tokens'][0]: r['tokens'][1:] for r in after['OPTIONS']
                      if r['tokens'][0] in wanted}
            self.assertEqual(wanted, actual)
            self.assertEqual(metadata['hydraulicInputSha256'], hydraulic_input_hash(row['raw']))


if __name__ == '__main__':
    unittest.main()
