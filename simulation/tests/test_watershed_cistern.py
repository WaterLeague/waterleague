"""회원 이용조의 원본 결속·집수 중복·견적과 물리 입력 독립성."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from waterleague_sim.run_watershed_job import inputs, CATALOG_HASH
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.ingestion.published_network import digest
from waterleague_sim.costing.cistern_reference import snapshot


def design():
    fixture = Path(__file__).parents[2]/'frontend/src/domains/watershed/view/fixtures/public-hydraulic-cistern-job.json'
    return json.loads(fixture.read_text())['design']


def packed(value):
    raw=json.dumps(value,sort_keys=True)
    return {'modelHash':CATALOG_HASH,'placements':raw,'inputHash':digest((CATALOG_HASH+'\n'+raw).encode())}


class CisternTests(unittest.TestCase):
    def test_quote_does_not_change_hydraulics_and_original_rain_area_is_preserved(self):
        value=design();result=inputs(packed(value))
        del value['cisternCosting']
        unpriced=inputs(packed(value))
        self.assertEqual(result[2:4],unpriced[2:4])
        metadata=result[5]['networkCistern']
        self.assertEqual(metadata['catchmentPartition']['originalAreaM2'],13729.38)
        self.assertEqual(metadata['facilities'][0]['capacityM3'],4.7)
        self.assertEqual(snapshot(value['placements'],value['cistern'])['items'][0]['equivalentUnits'],2)

    def test_catchment_overlap_source_shape_and_identifiers_are_verified_again(self):
        for patch in ({'subcatchmentId':'S1'},{'sourceNetworkSha256':'0'*64},
                {'id':'Bio1'},{'catalogHash':'0'*64},{'captureAreaM2':13729.38},
                {'depthAreaCurve':[{'depthM':0,'areaM2':2.35},{'depthM':2,'areaM2':3}]}):
            value=design();value.pop('cisternCosting');value['cistern'].update(patch)
            with self.assertRaises(FloodModelError): inputs(packed(value))
        value=design();value.pop('cisternCosting');value['placements'][0]['subcatchmentId']='S9'
        with self.assertRaisesRegex(FloodModelError,'SHARED_CATCHMENT'): inputs(packed(value))

    def test_shared_original_catchment_retargets_lid_only_to_free_impervious_partition(self):
        value=design(); value.pop('cisternCosting'); value.pop('costing',None)
        value['cistern']['schemaVersion']=3
        value['placements'][0]['subcatchmentId']='S9'
        result=inputs(packed(value))
        transformation=result[5]
        self.assertEqual(transformation['sourceDesign']['placements'][0]['subcatchmentId'],'S9')
        self.assertEqual(transformation['sourceCatchmentAssignments'][0]['executionCatchmentId'],'S9')
        partition=transformation['networkCistern']['catchmentPartition']
        self.assertEqual(partition['coverId'],'WLCT_Cistern1_R')
        self.assertEqual(transformation['facilities'][0]['subcatchmentId'],partition['imperviousBypassId'])
        value['placements'][0]['treatedImperviousM2']=13729.38
        with self.assertRaisesRegex(FloodModelError,'SHARED_CAPTURE_AREA_EXCEEDED'):
            inputs(packed(value))

    def test_multiple_lids_cannot_each_reuse_the_same_remaining_impervious_area(self):
        value=design();value.pop('cisternCosting');value.pop('costing',None)
        value['cistern'].update(schemaVersion=3,captureAreaM2=13567.03)
        value['placements'][0]['subcatchmentId']='S9'
        value['placements'].append(deepcopy(value['placements'][0])|{'id':'Second'})
        with self.assertRaisesRegex(FloodModelError,'SHARED_CAPTURE_AREA_EXCEEDED'):
            inputs(packed(value))

    def test_covered_legacy_lid_cannot_drop_rainfall_inside_shared_cistern_partition(self):
        from waterleague_sim.run_watershed_job import CATALOG
        value=design();value.pop('cisternCosting');value.pop('costing',None)
        value['cistern']['schemaVersion']=3
        item=value['placements'][0]
        item.update(subcatchmentId='S9',facilityType='RAINWATER_CISTERN')
        item['parameters']=json.loads(CATALOG.read_bytes())['templates']['RAINWATER_CISTERN']['parameters']
        with self.assertRaisesRegex(FloodModelError,'SHARED_COVERED_LID_UNSUPPORTED'):
            inputs(packed(value))
