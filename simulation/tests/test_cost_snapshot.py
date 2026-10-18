import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.costing.snapshot import archive, CostEvidenceError
from waterleague_sim.shared_model import resolve

ROOT = Path(__file__).resolve().parents[2]


class CostSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT/'frontend/src/domains/cost/view/fixtures/costRecord.json').read_text())
        cls.quote = cls.record['estimate']
        cls.model, _, _ = resolve({'district_id':cls.quote['districtId'], 'cell_id':cls.quote['cellId'],
                                  'model_hash':cls.quote['siteModelHash']})
        cls.placement = {'cellId':'G1','facilityType':'PERMEABLE_PAVEMENT','areaM2':20.25}

    def request(self, quote):
        raw = json.dumps(quote, ensure_ascii=False, separators=(',',':'))
        return {'costSnapshotRaw':raw,'costSnapshotSha256':hashlib.sha256(raw.encode()).hexdigest(),
                'installationCostKrw':'2227500.00'}

    def test_exact_archive_and_existing_record_absence(self):
        with tempfile.TemporaryDirectory() as path:
            directory = Path(path)
            missing = archive({}, self.model, self.placement, directory)
            self.assertEqual(missing['status'],'NOT_RECORDED')
            self.assertFalse((directory/'cost-snapshot.json').exists())
            request = self.request(self.quote)
            result = archive(request, self.model, self.placement, directory)
            self.assertEqual(result,self.record)
            self.assertEqual((directory/'cost-snapshot.json').read_bytes(),request['costSnapshotRaw'].encode())
            self.assertTrue((directory/'cost_snapshot.py').is_file())

    def test_rehashed_change_still_rejected_against_original_model(self):
        edits = {'cellId':'G2','siteModelHash':'f'*64,'quantityM2':20.26,'unitCostKrw':350000,
                 'budgetChargeKrw':0,'completeInstalledCostKrw':2227500,'historicalPriceEligible':True,
                 'costSourceSha256':'e'*64,'source':dict(self.quote['source'],referenceYear=2026)}
        with tempfile.TemporaryDirectory() as path:
            for key,value in edits.items():
                with self.subTest(key=key):
                    changed = copy.deepcopy(self.quote)
                    changed[key] = value
                    with self.assertRaises(CostEvidenceError):
                        archive(self.request(changed), self.model, self.placement, path)
            request = self.request(self.quote)
            request['installationCostKrw']='1'
            with self.assertRaises(CostEvidenceError): archive(request,self.model,self.placement,path)
            request['costSnapshotSha256']='0'*64
            with self.assertRaises(CostEvidenceError): archive(request,self.model,self.placement,path)
            with self.assertRaises(CostEvidenceError): archive({'costSnapshotSha256':'0'*64},self.model,self.placement,path)
            self.assertFalse((Path(path)/'cost-snapshot.json').exists())


if __name__ == '__main__':
    unittest.main()
