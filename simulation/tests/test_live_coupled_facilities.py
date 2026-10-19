"""직접 응답·시설·관망·지표의 결속과 비개입 관측·변조 거부 검증."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.forcing.live_network_rainfall import compile_network, FACILITY_OBSERVER
from waterleague_sim.ingestion import live
from waterleague_sim.reference.coupled_facilities import coupled_facility_case
from simulation.tests.test_coupled_facilities import DESIGN
from simulation.tests.test_flood_attribution import policy
from simulation.tests.test_live_network_rainfall import case
from run_live_surface import execute

ROOT=Path(__file__).resolve().parents[2]


def designed(kinds=('BIORETENTION','INFILTRATION_TRENCH')):
    model=case()
    source=deepcopy(DESIGN)
    source['placements']=[p for p in source['placements'] if p['facilityType'] in kinds]
    model['connectedFacilityDesign']=coupled_facility_case(source)['connectedFacilityDesign']
    return model


def context(root,model,result):
    network=json.loads((root/'network/network-result.json').read_text())
    surface=json.loads((root/'surface/surface-result.json').read_text())
    return policy()['context'] | {'metricSpecificationSha256':digest(model['evaluationMetrics']),
        'engineSha256':engine_signature(network,surface,result)}


class LiveFacilityTests(unittest.TestCase):
    def test_cover_unbound_design_and_existing_lid_rejected_before_acquisition(self):
        with tempfile.TemporaryDirectory() as temp:
            for mode in ('cover','oversized-geometry','unbound','missing-metrics'):
                model=designed(('RAINWATER_CISTERN',)) if mode=='cover' else designed()
                if mode=='oversized-geometry':model['connectedFacilityDesign']['placements'][0]['areaM2']=500
                if mode=='unbound':model['network']['inputText']+='\n[LID_USAGE]\nS1 Missing 1 1 0 0 0 0\n'
                if mode=='missing-metrics':model.pop('evaluationMetrics')
                specification=model.pop('observedRainfall')
                rainfall={k:specification[k] for k in ('startUtc','endUtc','stationByTriangle','stationByCatchment','assignmentEvidence')}
                with self.subTest(mode=mode),patch.object(live,'observed_forcing') as fetch:
                    with self.assertRaises(FloodModelError):execute({'mode':'coupled','model':model,'rainfall':rainfall},Path(temp)/mode,'secret')
                    fetch.assert_not_called()
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_source_change_during_calculation_rejects_result(self):
        from waterleague_sim.engine import coupled_flood
        source=Path(coupled_flood.__file__).read_bytes()
        original=coupled_flood.hashlib.sha256
        observed=[0]
        def changed(raw=b''):
            if raw==source:
                observed[0]+=1
                if observed[0]>1:return original(b'changed-during-run')
            return original(raw)
        with tempfile.TemporaryDirectory() as temp,patch.object(coupled_flood.hashlib,'sha256',side_effect=changed):
            path=Path(temp)/'case'
            with self.assertRaisesRegex(FloodModelError,'SOURCE_CHANGED_DURING_RUN'):run_coupled(case(),path)
            self.assertFalse((path/'coupled-result.json').exists())

    def test_real_engine_composition_replay_and_tampered_source(self):
        target=os.environ.get('LIVE_FACILITY_EVIDENCE_DIR')
        if target:
            root=Path(target).resolve();self.assertFalse(root.exists());root.mkdir(parents=True)
        else:
            temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='live-facility-');self.addCleanup(temp.cleanup);root=Path(temp.name)
        model=designed();original=deepcopy(model)
        prepared,rain=compile_network(model['network'],model['observedRainfall'])
        raw,facilities=compile_design(prepared['inputText'].encode(),model['connectedFacilityDesign'])
        legacy=deepcopy(model)
        legacy['network'],_=compile_network(model['network'],model['observedRainfall'])
        reference=ROOT/'data/derived/rainfall/kma-421-202208081800-202208082359-disaster-v1.json'
        legacy['observedRainfall']={k:v for k,v in model['observedRainfall'].items() if k not in
            ('sourceType','stationByCatchment','stations')} | {'schemaVersion':1,
            'stations':[{'file':reference.name,'sha256':file_digest(reference)}]}
        common=case() | {'networkObserverPolicy':FACILITY_OBSERVER}
        cases={'common-baseline':common,'baseline':case(),'design':model,'replay':model,'legacy':legacy,
               'bioretention':designed(('BIORETENTION',)) | {'networkObserverPolicy':FACILITY_OBSERVER}, 'swale':designed(('VEGETATIVE_SWALE',)),'mixed':designed(('BIORETENTION','INFILTRATION_TRENCH','VEGETATIVE_SWALE'))}
        results={}
        with patch.object(live,'fetch_range',side_effect=AssertionError('재생 중 네트워크 금지')):
            for name,source in cases.items():
                path=root/name
                result=results[name]=run_coupled(source,path)
                record=read_coupled_record(path,file_digest(path/'coupled-result.json'),context(path,source,result))
                self.assertEqual(record['numericalStatus'],result['numericalStatus'])
                self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']),1e-8)
                self.assertLess(abs(result['observedRainfall']['volumeResidualM3']),1e-8)
                if name!='legacy':self.assertLess(abs(result['networkRainfall']['nativeVolumeResidualM3']),1e-8)
        self.assertEqual(context(root/'common-baseline',common,results['common-baseline'])['engineSha256'],
                         context(root/'bioretention',cases['bioretention'],results['bioretention'])['engineSha256'])
        self.assertEqual(results['common-baseline']['balance'],results['baseline']['balance'])
        self.assertEqual((root/'common-baseline/network/network.out').read_bytes(),(root/'baseline/network/network.out').read_bytes())
        self.assertEqual(original,model)
        self.assertEqual(json.loads((root/'design/coupled-input.json').read_text()),original)
        self.assertEqual((root/'design/rainfall-network.inp').read_text(),prepared['inputText'])
        self.assertEqual((root/'design/facility-network.inp').read_bytes(),raw)
        self.assertEqual(json.loads((root/'design/connected-facility-design.json').read_text()),facilities)
        self.assertEqual(results['bioretention']['numericalStatus'],'PASSED')
        self.assertEqual(results['design']['numericalStatus'],'FAILED')
        self.assertEqual(results['design']['connectedFacilities']['quality']['failedFacilityIds'],['WL_Trench'])
        self.assertEqual(results['swale']['connectedFacilities']['quality']['failedFacilityIds'],['WL_Swale'])
        for name in ('replay','legacy'):
            for key in ('balance','evaluationMetrics','connectedFacilities'):
                self.assertEqual(results['design'][key],results[name][key])
            self.assertEqual((root/'design/network/network.out').read_bytes(),(root/name/'network/network.out').read_bytes())
        for name in ('network/network.inp','network-frames.jsonl','exchange-ledger.jsonl'):
            self.assertEqual((root/'design'/name).read_bytes(),(root/'replay'/name).read_bytes())
        self.assertNotEqual(results['baseline']['evaluationMetrics']['raw'],results['design']['evaluationMetrics']['raw'])
        for row in results['design']['connectedFacilities']['final']:
            self.assertGreater(row['inflowM3'],0)
            self.assertEqual(row['numericalStatus'],'FAILED' if row['swmmId']=='WL_Trench' else 'PASSED')
        # 결과·목록까지 다시 해시해도 실제 실행 입력과 원 설계가 다르면 승인하지 않는다.
        path=root/'design/network/network.inp';before=path.read_bytes()
        result_path=root/'design/coupled-result.json';result_raw=result_path.read_bytes()
        network_path=root/'design/network/network-result.json';network_raw=network_path.read_bytes()
        path.write_bytes(before.replace(b'WL_AWS_G401',b'G'))
        network=json.loads(network_raw);network['files']['network.inp']=file_digest(path)
        network_path.write_text(json.dumps(network))
        changed=deepcopy(results['design']);changed['files']['network/network.inp']=file_digest(path)
        changed['files']['network/network-result.json']=file_digest(network_path);result_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(EvaluationError,'RAIN_INPUT_MISMATCH'):
            read_coupled_record(root/'design',file_digest(result_path),context(root/'design',model,changed))
        path.write_bytes(before);network_path.write_bytes(network_raw);result_path.write_bytes(result_raw)
        summary={'classification':'REAL_ARCHIVED_RAIN_SYNTHETIC_NETWORK_AND_TERRAIN_NOT_SEOUL',
            'productionPublished':False,'originalInputPreserved':True,'sameInputReplay':True,
            'readOnlyObserverOutUnchanged':True,'cases':{name:{'status':r['numericalStatus'],
                'rawMetrics':r['evaluationMetrics']['raw'],'balance':r['balance'],
                'facilityQuality':r.get('connectedFacilities',{}).get('quality')} for name,r in results.items()}}
        (root/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
