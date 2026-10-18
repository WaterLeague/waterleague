"""이용조의 강우 면적 보존과 수두 지배 배수·역류 검사."""
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


class CisternNetworkTests(unittest.TestCase):
    def test_rain_area_width_and_unsupported_capture_protection(self):
        raw = source(); spec = design(raw)
        derived, evidence = compile_cistern(raw, spec)
        rows = [r['tokens'] for r in records(derived)[1]['SUBCATCHMENTS']]
        self.assertAlmostEqual(sum(float(r[3])*10000 for r in rows), 100)
        for row in rows:
            self.assertAlmostEqual(float(row[5])/(float(row[3])*10000), .1)
        self.assertEqual(evidence['catchmentPartition']['coverRainfallRoute'], 'BYPASS_CATCHMENT_TO_ORIGINAL_OUTLET')
        self.assertNotIn('LID_USAGE', records(derived)[1])
        self.assertEqual(compile_cistern(raw,spec), (derived,evidence))
        repeated=deepcopy(spec);repeated['sourceNetworkSha256']=evidence['derivedNetworkSha256']
        repeated['id']='Second'
        with self.assertRaisesRegex(FloodModelError, 'ALREADY_DERIVED'):
            compile_cistern(derived,repeated)
        for field, value in (('captureAreaM2', 100), ('footprintM2', .5), ('sourceNetworkSha256', '0'*64)):
            invalid=deepcopy(spec);invalid[field]=value
            with self.assertRaises(FloodModelError): compile_cistern(raw, invalid)
        mixed=raw.replace(b'0.01 100 10',b'0.01 80 10')
        with self.assertRaisesRegex(FloodModelError, 'FULLY_IMPERVIOUS'):
            compile_cistern(mixed,design(mixed))
        for before, after in ((b'0.01 100 10', b'bad 100 10'),
                (b'FLOW_UNITS CMS', b'FLOW_UNITS'), (b'TANK 0 3', b'TANK bad 3')):
            malformed=raw.replace(before,after)
            with self.assertRaises(FloodModelError): compile_cistern(malformed,design(malformed))

    def test_native_runoff_conservation_and_bidirectional_ports(self):
        with tempfile.TemporaryDirectory(prefix='wl-cistern-') as directory:
            root=Path(directory); results={}
            for key, backwater, flap in (('ordinary',False,True),('backwater',True,False),('flap',True,True)):
                raw=source(backwater=backwater)
                derived, metadata=compile_cistern(raw,design(raw,flap=flap))
                with EngineProcess('network',raw.decode(),root/(key+'-base'),native_duration=True) as p:
                    baseline=p.call('run',1)['result']
                with EngineProcess('network',derived.decode(),root/key,native_duration=True) as p:
                    result=p.call('run',1)['result']
                ledger=result_summary(metadata,result['initial'],result['final'])
                expected = 'FAILED' if key == 'ordinary' else 'PASSED'
                self.assertEqual(baseline['numericalStatus'], expected)
                self.assertEqual(result['numericalStatus'], expected, result['numericalQuality'])
                if expected == 'FAILED':
                    self.assertIn('ROUTING_VOLUME_RESIDUAL_EXCEEDED', result['numericalQuality']['failureReasons'])
                self.assertEqual(ledger['numericalStatus'],'PASSED',ledger)
                self.assertAlmostEqual(baseline['final']['totals']['runoffInflowM3'],result['final']['totals']['runoffInflowM3'],places=7)
                frames=[json.loads(row) for row in (root/key/'network-frames.jsonl').read_text().splitlines()]
                flows=[f['links']['WLCT_Cistern_D']['flowM3s'] for f in frames]
                results[key]=(result, min(flows))
            self.assertLess(results['backwater'][1],-1e-7)
            self.assertGreaterEqual(results['flap'][1],-1e-12)
            self.assertGreater(results['ordinary'][0]['final']['nodes']['WLCT_Cistern']['storageM3'],0)


if __name__=='__main__': unittest.main()
