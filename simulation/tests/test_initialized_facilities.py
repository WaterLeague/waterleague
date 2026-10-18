"""연결 시설 선행 관측·시간 범위·수지 차분·기간/시드 재현 검사."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from waterleague_sim.engine import facility_network
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.initialized_facilities import evaluation_ledger, run_initialized_facilities
from waterleague_sim.forcing.network_initialization import prepare_initialized_network
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.initialized_facilities import inputs

ROOT = Path(__file__).resolve().parents[2]
DESIGN = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_text())


class NetworkInitializationInputTests(unittest.TestCase):
    def test_raw_reconstruction_preserves_hydraulics_and_observation_timing(self):
        model, spec, init = inputs()
        model['inputText'] += '\n[EVAPORATION]\nCONSTANT 2\nDRY_ONLY YES\nRECOVERY RC\n[CURVES]\nRC RECOVERY 1 1\nRC 12 1\n'
        original = deepcopy((model, spec, init))
        result = prepare_initialized_network(model, spec, init)
        self.assertEqual((model, spec, init), original)
        before, after = records(model['inputText'].encode())[1], records(result.model['inputText'].encode())[1]
        for section in before.keys() - {'RAINGAGES', 'EVAPORATION', 'SUBCATCHMENTS', 'TIMESERIES'}:
            self.assertEqual([r['tokens'] for r in before[section]], [r['tokens'] for r in after[section]])
        self.assertEqual(before['SUBCATCHMENTS'][0]['tokens'][2:], after['SUBCATCHMENTS'][0]['tokens'][2:])
        self.assertEqual(after['RAINGAGES'][0]['tokens'], ['WL_INIT_G421', 'INTENSITY', '0:01', '1.0', 'TIMESERIES', 'WL_INIT_R421'])
        self.assertEqual([r['tokens'] for r in after['EVAPORATION']],
                         [['TIMESERIES','WL_INIT_PET'],['DRY_ONLY','YES'],['RECOVERY','RC']])
        rain = [r['tokens'] for r in after['TIMESERIES'] if r['tokens'][0] == 'WL_INIT_R421']
        self.assertTrue(all(row[2].endswith(':01') for row in rain))
        self.assertAlmostEqual(sum(float(row[3])/60 for row in rain), 231., places=9)
        self.assertEqual(result.summary['stations'][0]['warmupDepthMm'], 146.)
        self.assertEqual(result.summary['stations'][0]['evaluationDepthMm'], 85.)
        self.assertFalse(result.summary['rankingEligible'])
        self.assertEqual(result.summary['originalSha256'], hashlib.sha256(model['inputText'].encode()).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'sources'
            result.archive(path)
            repeated = prepare_initialized_network(model, spec, init, root=path)
            self.assertEqual(repeated.model, result.model)
            self.assertEqual(repeated.summary, result.summary)

    def test_missing_period_station_weather_and_unsupported_forcing_rejected(self):
        model, spec, init = inputs()
        for modified, observation, initialization, code in (
            (model, spec, init | {'days':14}, 'MODEL_CLOCK_MISMATCH'),
            (model, spec | {'stationByCatchment':{}}, init, 'ASSIGNMENT_INCOMPLETE'),
            (model, spec, init | {'weatherReference':{}}, 'WEATHER_BINDING_INVALID'),
            (model | {'inputText':model['inputText']+'\n[ADJUSTMENTS]\nRAIN 1 1 1 1 1 1 1 1 1 1 1 1\n'}, spec, init, 'UNSUPPORTED_FORCING'),
            (model | {'inputText':model['inputText'].replace('WET_STEP 00:00:01','WET_STEP 00:00:10')}, spec, init, 'SECOND_HYDROLOGY_REQUIRED')):
            with self.assertRaisesRegex(FloodModelError, code):
                prepare_initialized_network(modified, observation, initialization)
        model, spec, init = inputs(28)
        with self.assertRaisesRegex(FloodModelError, 'ANTECEDENT_BINDING_INVALID'):
            prepare_initialized_network(model, spec, init)

    def test_external_inflow_and_stage_cannot_extrapolate_over_warmup(self):
        model, spec, init = inputs()
        series = '\n[TIMESERIES]\nEXTERNAL 08/01/2022 09:00 1\nEXTERNAL 08/08/2022 14:59 2\n'
        for suffix in ('\n[INFLOWS]\nTANK FLOW EXTERNAL FLOW 1 1 0\n', ''):
            candidate = deepcopy(model)
            if suffix:
                candidate['inputText'] += suffix + series
            else:
                candidate['inputText'] = candidate['inputText'].replace('OUT 0 FIXED 0 NO', 'OUT 0 TIMESERIES EXTERNAL NO') + series
            with self.assertRaisesRegex(FloodModelError, 'EXTERNAL_SERIES_EVIDENCE_REQUIRED'):
                prepare_initialized_network(candidate, spec, init)
            candidate['externalTimeSeries'] = {'EXTERNAL':{'evidence':'NUMERICAL_TEST_ONLY', 'maximumIntervalSeconds':8*86400}}
            result = prepare_initialized_network(candidate, spec, init)
            self.assertEqual(len(result.summary['externalTimeSeries']),1)
            candidate['inputText'] = candidate['inputText'].replace('EXTERNAL 08/01/2022 09:00', 'EXTERNAL 08/01/2022 09:01')
            with self.assertRaisesRegex(FloodModelError, 'EXTERNAL_SERIES_COVERAGE_INCOMPLETE'):
                prepare_initialized_network(candidate, spec, init)


@unittest.skipUnless(facility_network.library_path().exists(), '연결 시설 엔진 설치 필요')
class InitializedFacilityNativeTests(unittest.TestCase):
    def test_observed_periods_seeds_window_balance_and_exact_replay(self):
        target = os.environ.get('INITIALIZED_FACILITY_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
            root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='initial-lid-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        results, networks = {}, {}
        for name, days, seed in (('7d-dry',7,0), ('7d-wet',7,100), ('14d-dry',14,0),
                                 ('14d-wet',14,100), ('replay-14d-dry',14,0)):
            design = deepcopy(DESIGN)
            for placement in design['placements']:
                if placement['facilityType'] != 'VEGETATIVE_SWALE':
                    placement['initialSaturationPercent'] = seed
            model, spec, init = inputs(days)
            output = root/name
            result = results[name] = run_initialized_facilities(model,spec,init,design,output)
            network = networks[name] = json.loads((output/'network/network-result.json').read_text())
            self.assertEqual(result['numericalStatus'],'PASSED')
            self.assertEqual(network['convergence']['nonConvergedSteps'],0)
            self.assertTrue(result['evaluationLedger']['scoreExcludesWarmup'])
            self.assertIsNone(result['evaluationLedger']['peakFlowM3s'])
            initial = json.loads((output/'evaluation-initial-state.json').read_text())
            self.assertEqual(initial['totals']['timeSeconds'], days*86400)
            self.assertEqual(len(initial['facilities']),4)
            self.assertEqual(result['evaluationLedger'],evaluation_ledger(initial,network['final']))
            self.assertGreater(next(u for u in initial['facilities'] if u['swmmId']=='WL_Bioretention')['soilMoisture'],.08)
            self.assertNotEqual(initial['facilities'],network['initial']['facilities'])
            for unit in result['evaluationLedger']['facilities']:
                final = next(u for u in network['final']['facilities'] if u['swmmId']==unit['swmmId'])
                self.assertLess(unit['inflowM3'],final['inflowM3'])
                self.assertLess(abs(unit['balanceResidualM3']),unit['allowedResidualM3'])
            report = (output/'network/network.rpt').read_text(encoding='cp1252')
            precipitation = float(re.search(r'Total Precipitation\s*\.+\s+[-\d.]+\s+([-\d.]+)',report)[1])
            observation = result['initialization']['stations'][0]
            self.assertAlmostEqual(precipitation,observation['warmupDepthMm']+observation['evaluationDepthMm'],places=3)
            print(name,result['numericalStatus'],flush=True)
        for key in ('evaluationLedger','evaluationInitialFacilities','evaluationFinalFacilities'):
            self.assertEqual(results['14d-dry'][key],results['replay-14d-dry'][key])
        self.assertEqual((root/'14d-dry/network/network.out').read_bytes(),
                         (root/'replay-14d-dry/network/network.out').read_bytes())
        original = json.loads((root/'14d-dry/evaluation-initial-state.json').read_text())
        final = networks['14d-dry']['final']
        future = deepcopy(original)
        future['facilities'][0]['hydrologyTimeSeconds'] += 1
        with self.assertRaisesRegex(FloodModelError,'HYDROLOGY_CLOCK_MISMATCH'):
            evaluation_ledger(future,final)
        altered = deepcopy(final)
        altered['facilities'][0]['surfaceOutflowM3'] += 10000
        self.assertEqual(evaluation_ledger(original,altered)['numericalStatus'],'FAILED')
        def measures(result):
            return {'routingOutflowM3':result['evaluationLedger']['routingTotals']['outflowM3'],
                'facilities':{row['swmmId']:{key:row[key] for key in ('inflowM3','evaporationM3',
                    'infiltrationM3','surfaceOutflowM3','drainOutflowM3','initialStorageM3','finalStorageM3')}
                    for row in result['evaluationLedger']['facilities']}}
        summary = {'schemaVersion':1,'classification':'OBSERVED_WEATHER_ON_SYNTHETIC_NETWORK',
            'rankingEligible':False,'exactReplay':True,'cases':{name:measures(result) for name,result in results.items()},
            'seedPolicy':'LID_INIT_SAT_0_OR_100_EXCEPT_UNSUPPORTED_SWALE_SEED',
            'limitations':['시드는 현장 관측이 아니며 식생수로 InitSat 미지원 유지',
                '같은 형상·재료·관측의 기간/시드 비교이며 전체 서울 수렴 인증 아님',
                '관망 단독 실행이며 2D 지표 선행 상태는 별도 연결 필요']}
        (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
