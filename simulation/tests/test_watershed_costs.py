"""참고 원가의 미산정·변조 차단 및 기존 물리 입력 보존."""
import copy
import hashlib
import json
import unittest
from waterleague_sim.costing.watershed import CATALOG, CATALOG_HASH, snapshot, verify
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.run_watershed_job import CATALOG as NETWORK, CATALOG_HASH as NETWORK_HASH, inputs


class WatershedCostsTests(unittest.TestCase):
    def test_unknown_price_is_not_zero_and_cost_changes_cannot_be_hidden(self):
        catalog=json.loads(CATALOG.read_text())
        placements=[{'id':'B','facilityType':'BIORETENTION','areaM2':100.01},
                    {'id':'S','facilityType':'VEGETATIVE_SWALE','areaM2':100}]
        cost=snapshot(placements,catalog)
        self.assertEqual(cost['knownReferenceSubtotalKrw'],56005600)
        self.assertIsNone(cost['items'][1]['referenceAmountKrw'])
        self.assertEqual(cost['unpricedPlacementIds'],['S'])
        self.assertIsNone(snapshot(placements[1:],catalog)['knownReferenceSubtotalKrw'])
        design={'schemaVersion':1,'basis':'REFERENCE','placements':placements,'costing':cost}
        self.assertEqual(hashlib.sha256(verify(design)).hexdigest(),CATALOG_HASH)
        for change in ('amount','quantity','source','missing','hash'):
            changed=copy.deepcopy(design)
            if change=='amount': changed['costing']['knownReferenceSubtotalKrw']=0
            if change=='quantity': changed['placements'][0]['areaM2']=101
            if change=='source': changed['costing']['source']['year']=2026
            if change=='missing': changed['costing']['unpricedPlacementIds']=[]
            if change=='hash': changed['costing']['catalogHash']='0'*64
            with self.subTest(change=change), self.assertRaises(FloodModelError): verify(changed)

    def test_cost_snapshot_does_not_change_existing_hydraulic_input(self):
        catalog=json.loads(NETWORK.read_text())
        template=catalog['templates']['BIORETENTION']
        design={'schemaVersion':1,'basis':catalog['designBasis'],'placements':[
            {'id':'Bio1','facilityType':'BIORETENTION','subcatchmentId':'S1','areaM2':100,
             'replacedImperviousM2':100,'treatedImperviousM2':1000,
             'initialSaturationPercent':template['initialSaturationPercent'],'parameters':template['parameters']}]}
        def request(value):
            raw=json.dumps(value,sort_keys=True)
            return {'modelHash':NETWORK_HASH,'placements':raw,
                    'inputHash':hashlib.sha256((NETWORK_HASH+'\n'+raw).encode()).hexdigest()}
        old=inputs(request(design))
        design['costing']=snapshot(design['placements'],json.loads(CATALOG.read_text()))
        new=inputs(request(design))
        self.assertEqual(old[2:6],new[2:6])


if __name__=='__main__': unittest.main()
