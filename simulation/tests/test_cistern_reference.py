import copy
import hashlib
import json
from pathlib import Path
import unittest
from waterleague_sim.costing.cistern_reference import verify, source_artifacts
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.run_watershed_job import inputs, CATALOG_HASH

FIXTURE=Path(__file__).parent/'fixtures/member-cistern-costs-v1.json'
class CisternReferenceTests(unittest.TestCase):
    def test_capacity_source_components_and_unchanged_hydraulic_input(self):
        design=json.loads(FIXTURE.read_text())
        self.assertTrue(verify(design))
        first,second=design['cisternCosting']['items']
        self.assertEqual(first['capacityM3'],4.7)
        self.assertEqual(first['equivalentUnits'],2)
        self.assertEqual(first['quotes'][2]['quotedSubtotalKrw'],5714000)
        self.assertIsNone(first['quotes'][2]['components']['LOG'])
        self.assertIsNone(second['equivalentUnits'])
        self.assertEqual(second['quotes'],[])
        self.assertEqual(len(source_artifacts()),2)
        def prepare(value):
            raw=json.dumps(value,sort_keys=True)
            return inputs({'modelHash':CATALOG_HASH,'placements':raw,'inputHash':hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()})
        priced=prepare(design)
        del design['cisternCosting']
        unpriced=prepare(design)
        self.assertEqual(priced[2:4],unpriced[2:4])
        self.assertIsNone(verify(design))
    def test_rejects_changed_capacity_missing_amount_and_catalog(self):
        original=json.loads(FIXTURE.read_text())
        changed=[]
        d=copy.deepcopy(original);d['placements'][0]['areaM2']=2.36;changed.append(d)
        d=copy.deepcopy(original);d['cisternCosting']['catalogHash']='0'*64;changed.append(d)
        d=copy.deepcopy(original);d['cisternCosting']['items'][0]['quotes'][2]['components']['LOG']=0;changed.append(d)
        d=copy.deepcopy(original);d['cisternCosting']['items'][0]['quotes'][0]['quotedSubtotalKrw']+=1;changed.append(d)
        d=copy.deepcopy(original);d['cisternCosting']['items'].pop();changed.append(d)
        for d in changed:
            with self.assertRaises(FloodModelError):verify(d)
