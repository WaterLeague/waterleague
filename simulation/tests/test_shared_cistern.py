"""합성 수치 진단의 집수·덮개·LID 중복과 원 유출 계수 보존 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.cistern_network import compile_cistern, SHARED_METHOD
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine import flow_connections, facility_metrics
from waterleague_sim.engine.connected_storage import result_summary
from waterleague_sim.ingestion.published_network import records, digest
from waterleague_sim.reference.cistern_network import source, design, hydrology_series
from waterleague_sim.watershed_cistern import prepare_lids

FIXTURE = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_bytes())


def combined(percent=80, facility_index=0):
    raw = source(backwater=True).replace(b'0.01 100 10', f'0.01 {percent} 10'.encode())
    cistern, metadata = compile_cistern(raw, design(raw) | {'schemaVersion':3})
    item = deepcopy(FIXTURE['placements'][facility_index])
    item.update(areaM2=5, replacedImperviousM2=5, treatedImperviousM2=10)
    original = {**deepcopy(FIXTURE), 'placements':[item]}
    adjusted, execution, assignments, width = prepare_lids(cistern, original, metadata)
    strategy, transformation = compile_design(adjusted, execution)
    transformation.update(networkCistern=metadata, sourceCatchmentAssignments=assignments,
                          sourceDesign=original, sharedCatchmentWidth=width)
    return raw, cistern, strategy, metadata, original, transformation


class SharedCisternTests(unittest.TestCase):
    def test_capture_cover_and_remaining_impervious_pool_are_disjoint(self):
        for percent in (25, 80, 100):
            with self.subTest(percent=percent):
                raw = source().replace(b'0.01 100 10', f'0.01 {percent} 10'.encode())
                output, metadata = compile_cistern(raw, design(raw) | {'schemaVersion':3, 'captureAreaM2':10})
                rows = {r['tokens'][0]:r['tokens'] for r in records(output)[1]['SUBCATCHMENTS']}
                partition = metadata['catchmentPartition']
                self.assertEqual(metadata['method'], SHARED_METHOD)
                self.assertAlmostEqual(sum(float(r[3])*10000 for r in rows.values()),100)
                self.assertEqual(rows[partition['coverId']][2], 'TANK')
                self.assertEqual(float(rows[partition['coverId']][3])*10000,1)
                for key in ('captureId','coverId','imperviousBypassId'):
                    r=rows[partition[key]]
                    self.assertAlmostEqual(float(r[5])/(float(r[3])*10000),10/percent)
                if percent < 100:
                    self.assertEqual(rows['S1'][4:6],['0','10'])
                    self.assertAlmostEqual(float(rows['S1'][3])*10000,100-percent)

    def test_lid_uses_only_free_impervious_runoff_and_preserves_non_lid_width_ratio(self):
        for percent in (80,100):
            raw, cistern, strategy, metadata, original, transformed = combined(percent)
            partition=metadata['catchmentPartition']
            rows={r['tokens'][0]:r['tokens'] for r in records(strategy)[1]['SUBCATCHMENTS']}
            usage=records(strategy)[1]['LID_USAGE'][0]['tokens']
            self.assertEqual(original['placements'][0]['subcatchmentId'],'S1')
            self.assertEqual(usage[0],partition['imperviousBypassId'])
            self.assertNotEqual(usage[0],partition['coverId'])
            self.assertNotEqual(usage[0],partition['captureId'])
            remaining=percent-20-1-5
            self.assertAlmostEqual(float(usage[6]),100*10/remaining)
            self.assertEqual(usage[7:],['0','*','TANK','0'])
            self.assertAlmostEqual(float(rows[usage[0]][5])/remaining,10/percent)
            self.assertEqual(transformed['sharedCatchmentWidth']['sourceNetworkSha256'],digest(cistern))
            for label in ('captureId','coverId'):
                self.assertEqual(rows[partition[label]],next(r['tokens'] for r in records(cistern)[1]['SUBCATCHMENTS'] if r['tokens'][0]==partition[label]))

    def test_source_flow_graph_binds_original_pool_to_execution_catchment_and_cover(self):
        raw, _, strategy, _, original, transformed = combined()
        sources={name:digest(value) for name,value in (
            ('original.inp',raw),('baseline-input.inp',raw),('strategy-input.inp',strategy),
            ('design.json',flow_connections.encode(original)))}
        value=flow_connections.published_network(raw,raw,strategy,original,transformed,sources,[])
        budget=next(b for b in value['areaBudgets'] if b['surfaceClass']=='IMPERVIOUS')
        cover=next(a for a in budget['allocations'] if a.get('role')=='CISTERN_COVER_RAIN_BYPASS')
        self.assertEqual(cover['targetNodeId'],'catchment:WLCT_CISTERN_R')
        facility=next(n for n in value['nodes'] if n['kind']=='LID_FACILITY')
        self.assertEqual(facility['sourceCatchmentId'],'S1')
        self.assertEqual(facility['executionCatchmentId'],'WLCT_Cistern_B')

    def test_rejects_empty_remaining_pool_and_new_partition_id_collisions(self):
        raw=source()
        for patch in ({'captureAreaM2':99},{'captureAreaM2':100}):
            with self.assertRaises(FloodModelError): compile_cistern(raw,design(raw)|{'schemaVersion':3,**patch})
        collision=raw+b'\n[RAINGAGES]\nWLCT_Cistern_R INTENSITY 0:01 1 TIMESERIES RAIN\n'
        with self.assertRaisesRegex(FloodModelError,'ID_COLLISION'):
            compile_cistern(collision,design(collision)|{'schemaVersion':3})
        _,cistern,_,metadata,original,_=combined()
        with self.assertRaisesRegex(FloodModelError,'SHARED_SOURCE_CHANGED'):
            prepare_lids(cistern+b'\n',original,metadata)

    def test_native_cover_partition_preserves_rain_evaporation_infiltration_and_runoff(self):
        with tempfile.TemporaryDirectory(prefix='wl-shared-cistern-') as directory:
            for percent in (25,80,100):
                raw=source(backwater=True).replace(b'0.01 100 10',f'0.01 {percent} 10'.encode())
                old,_=compile_cistern(raw,design(raw)|{'schemaVersion':2 if percent<100 else 1,'captureAreaM2':10})
                new,_=compile_cistern(raw,design(raw)|{'schemaVersion':3,'captureAreaM2':10})
                a=hydrology_series(old,Path(directory)/f'{percent}-old')
                b=hydrology_series(new,Path(directory)/f'{percent}-new')
                for name in a:
                    self.assertEqual(len(a[name]),len(b[name]))
                    for x,y in zip(a[name],b[name]):
                        self.assertAlmostEqual(x,y,delta=max(1e-9,abs(x)*2e-7),msg=name)

    @unittest.skipUnless(facility_metrics.library_path().is_file(),'관망 지표 엔진 설치 필요')
    def test_partial_storage_retains_native_volume_and_only_current_headroom_is_available(self):
        raw=source(backwater=True)
        derived,metadata=compile_cistern(raw,design(raw)|{'schemaVersion':3,'initialDepthM':.3})
        with tempfile.TemporaryDirectory(prefix='wl-shared-partial-') as directory:
            with EngineProcess('facility_metrics',derived.decode(),Path(directory)/'run',native_duration=True) as process:
                result=process.call('run',60)['result']
        node=result['initial']['nodes']['WLCT_Cistern']
        self.assertAlmostEqual(node['depthM'],.3)
        self.assertAlmostEqual(node['storageM3'],.3*0.028316846592/0.02832)
        item=result_summary(metadata,result['initial'],result['final'])['wholeRunLedger']['facilities'][0]
        self.assertEqual(item['initialStorageM3'],node['storageM3'])
        self.assertAlmostEqual(item['initialAvailableM3'],(1.4-.3)*0.028316846592/0.02832)
        self.assertIsNone(item['reuseM3'])
        self.assertEqual(item['reuseStatus'],'NOT_CALCULATED_NO_USE_DEMAND')

    @unittest.skipUnless(facility_metrics.library_path().is_file(),'관망 지표 엔진 설치 필요')
    def test_native_cistern_and_lid_share_one_hydraulic_run_with_preserved_capture_hydrology(self):
        with tempfile.TemporaryDirectory(prefix='wl-shared-ledger-') as directory:
            for percent in (80,100):
                for index in range(3):
                    raw,cistern,strategy,metadata,original,_=combined(percent,index)
                    results=[]
                    for name,inp in (('cistern',cistern),('combined',strategy)):
                        with EngineProcess('facility_metrics',inp.decode(),Path(directory)/f'{percent}-{index}-{name}',native_duration=True) as process:
                            results.append(process.call('run',60)['result'])
                    for result in results:
                        self.assertEqual(result['numericalStatus'],'PASSED',result['numericalQuality'])
                    lid = results[1]['final']['facilities'][0]
                    self.assertEqual(lid['swmmId'], 'WL_'+original['placements'][0]['id'])
                    self.assertGreater(lid['inflowM3'],0)
                    self.assertEqual(results[1]['final']['nodes'][metadata['facilities'][0]['nodeId']]['type'],2)


if __name__=='__main__': unittest.main()
