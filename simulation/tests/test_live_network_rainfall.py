"""관망·지표 강우의 원문 결속, 소유 면적, 실제 엔진 투입량 검사."""
from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.live_network_rainfall import compile_network, validate_network
from waterleague_sim.forcing.live_rainfall import capture
from waterleague_sim.forcing.observed_rainfall import compile_rainfall
from waterleague_sim.ingestion import live
from waterleague_sim.reference.coupled_facilities import coupled_facility_case
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from simulation.tests.test_flood_attribution import policy
from simulation.tests.test_live_surface_rainfall import START, END, response, specification
from run_live_surface import execute


def case():
    model = coupled_facility_case(None)
    model['surface']['schemaVersion'] = 2
    text = model['network']['inputText'].replace('01/01/2020','08/08/2022')
    text = text.replace('00:00:00','10:46:00').replace('00:02:01','10:48:01')
    # 시계 교체는 수문 단계 1초와 원 강우계의 분 값에 영향을 주지 않는다.
    model['network'].update(inputText=text, timeZone='UTC')
    spec = specification(model['surface'])
    spec['stationByCatchment'] = {'S1':'401'}
    spec['stations'].append({'stationId':'401','responses':[response('401')]})
    model['observedRainfall'] = spec
    return model


class LiveNetworkTests(unittest.TestCase):
    def test_shared_sources_split_area_and_preserve_original_options(self):
        model = case(); original = deepcopy(model)
        spec = model['observedRainfall']
        schedule = compile_rainfall(spec, model['surface'], 120, network_stations={'401'})
        prepared, summary = compile_network(model['network'], spec)
        self.assertEqual(model, original)
        self.assertIn('S1 WL_AWS_G401 TANK 0.01 100 10 1 0', prepared['inputText'])
        self.assertIn('WL_AWS_R401 08/08/2022 10:46:01', prepared['inputText'])
        self.assertIn('WL_AWS_R401 08/08/2022 10:48:01 0', prepared['inputText'])
        self.assertIn('G INTENSITY 0:01 1.0 TIMESERIES RAIN', prepared['inputText'])
        self.assertEqual(summary['catchmentAreasM2'], {'S1':100.})
        self.assertTrue(all(set(e['ratesMmHByStation']) == {'421'} for e in schedule.events))
        self.assertEqual({r['stationId']:r['surfaceAreaM2'] for r in schedule.summary['stations']},
                         {'401':0., '421':100.})
        for line in model['network']['inputText'].splitlines():
            if not line.startswith('S1 G '):
                self.assertIn(line, prepared['inputText'])

    def test_mapping_clock_modifiers_and_unbound_surface_fail_closed(self):
        model = case(); spec = model['observedRainfall']
        with self.assertRaisesRegex(FloodModelError, 'NETWORK_BINDING_REQUIRED'):
            compile_rainfall(spec, model['surface'], 120)
        for mapping in (None, {}, {'other':'401'}, {'S1':'401','extra':'421'}, {'S1':'not-station'}):
            value = deepcopy(spec); value['stationByCatchment'] = mapping
            with self.subTest(mapping=mapping), self.assertRaisesRegex(FloodModelError, 'ASSIGNMENT_INCOMPLETE'):
                validate_network(model['network'], value)
        for old, new in [('10:48:01','10:48:00'), ('WET_STEP 00:00:01','WET_STEP 00:01:00'),
                         ('FLOW_ROUTING DYNWAVE','FLOW_ROUTING KINWAVE')]:
            net = model['network'] | {'inputText':model['network']['inputText'].replace(old,new)}
            self.assertNotEqual(net, model['network'])
            with self.subTest(old=old), self.assertRaises(FloodModelError):
                validate_network(net, spec)
        for extra in ('[ADJUSTMENTS]\nRAINFALL 2 2 2 2 2 2 2 2 2 2 2 2',
                      '[LID_USAGE]\nS1 LID 1 1 1 0 0 0', '[FILES]\nUSE HOTSTART secret'):
            with self.subTest(extra=extra), self.assertRaisesRegex(FloodModelError, 'UNSUPPORTED_FORCING'):
                validate_network(model['network'] | {'inputText':model['network']['inputText']+'\n'+extra}, spec)

    def test_capture_queries_union_once_and_checks_network_before_query(self):
        model = case(); spec = model['observedRainfall']
        def fetched(station, *args):
            row = response(station)
            return {}, [(row['rawUtf8'].encode(), row['metadata'])]
        with patch.object(live, 'observed_forcing', side_effect=fetched) as fetch:
            value = capture(model['surface'],spec['stationByTriangle'],START,END,'secret', 'TEST',
                            network=model['network'],station_by_catchment={'S1':'401'})
            self.assertEqual([c.args[0] for c in fetch.call_args_list], ['401','421'])
            self.assertNotIn('secret',json.dumps(value))
        with patch.object(live,'observed_forcing') as fetch:
            with self.assertRaises(FloodModelError):
                capture(model['surface'],spec['stationByTriangle'],START,END,'secret','TEST',
                        network=model['network'],station_by_catchment={})
            fetch.assert_not_called()

    def test_missing_assignment_or_double_rainfall_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = case(); del model['observedRainfall']['stationByCatchment']
            with self.assertRaisesRegex(FloodModelError, 'ASSIGNMENT_INCOMPLETE'):
                run_coupled(model, Path(temporary)/'missing')
            model = case()
            index = model['networkRainfallTriangles']['S1'][0]
            model['observedRainfall']['stationByTriangle'][index] = '401'
            with self.assertRaisesRegex(FloodModelError, 'OWNERSHIP_INVALID'):
                run_coupled(model, Path(temporary)/'double')
            model = case(); model['surface']['rainfallOwner'][index] = 'SURFACE'
            with self.assertRaisesRegex(FloodModelError, 'OVERLAP'):
                run_coupled(model, Path(temporary)/'ownership')
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_cli_capture_path_and_shared_station_query_once(self):
        model = case(); spec = model.pop('observedRainfall')
        spec['stationByCatchment'] = {'S1':'421'}
        rainfall = {k:spec[k] for k in ('startUtc','endUtc','stationByTriangle','assignmentEvidence','stationByCatchment')}
        row = response()
        with tempfile.TemporaryDirectory() as temporary, patch.object(live,'observed_forcing',return_value=(
                {},[(row['rawUtf8'].encode(),row['metadata'])])) as fetch, patch(
                'waterleague_sim.engine.coupled_flood.run_coupled',return_value={'ok':True}) as run:
            self.assertEqual(execute({'mode':'coupled','model':model,'rainfall':rainfall},
                Path(temporary)/'run','secret'),{'ok':True})
            fetch.assert_called_once_with('421',START,END,'secret')
            self.assertEqual(run.call_args.args[0]['observedRainfall']['stationByCatchment'],{'S1':'421'})

    @unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
    def test_native_inputs_and_replay_are_identical(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(live,'fetch_range',side_effect=AssertionError('재생 네트워크 금지')):
                model = case()
                first = run_coupled(model, root/'a')
                saved = json.loads((root/'a/coupled-input.json').read_text())
                replay = run_coupled(saved, root/'b')
            legacy = deepcopy(model)
            legacy['network'], _ = compile_network(model['network'], model['observedRainfall'])
            reference = Path(__file__).resolve().parents[2]/'data/derived/rainfall/kma-421-202208081800-202208082359-disaster-v1.json'
            legacy['observedRainfall'] = {k:v for k,v in model['observedRainfall'].items()
                if k not in ('sourceType','stationByCatchment','stations')} | {'schemaVersion':1,
                'stations':[{'file':reference.name,'sha256':file_digest(reference)}]}
            without_metrics = deepcopy(model)
            without_metrics.pop('evaluationMetrics')
            raw_run = run_coupled(without_metrics, root/'without-metrics')
            self.assertEqual(first['networkRainfall'],raw_run['networkRainfall'])
            self.assertEqual(first['balance'],raw_run['balance'])
            old_engine = run_coupled(legacy, root/'old-engine')
            self.assertEqual(first['balance'],old_engine['balance'])
            self.assertEqual(first['evaluationMetrics'],old_engine['evaluationMetrics'])
            self.assertEqual((root/'a/network/network.out').read_bytes(),(root/'old-engine/network/network.out').read_bytes())
            self.assertEqual(first['numericalStatus'], 'PASSED')
            detail = first['networkRainfall']
            self.assertGreater(detail['expectedNetworkRainfallM3'],0)
            self.assertLess(abs(detail['nativeVolumeResidualM3']),1e-8)
            self.assertAlmostEqual(detail['expectedCombinedRainfallM3'],detail['appliedCombinedRainfallM3']-detail['unitConversionDifferenceM3'])
            self.assertEqual(first['networkRainfall'],replay['networkRainfall'])
            self.assertEqual(first['balance'],replay['balance'])
            network = json.loads((root/'a/network/network-result.json').read_text())
            surface = json.loads((root/'a/surface/surface-result.json').read_text())
            context = policy()['context'] | {'metricSpecificationSha256':digest(model['evaluationMetrics']),
                'engineSha256':engine_signature(network,surface,first)}
            self.assertTrue(read_coupled_record(root/'a',file_digest(root/'a/coupled-result.json'),context)['complete'])
            changed = deepcopy(first)
            changed['networkRainfall']['nativeInput']['grossRainfallM3'] = 0
            (root/'a/coupled-result.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(EvaluationError,'NETWORK_RAIN_VOLUME_MISMATCH'):
                read_coupled_record(root/'a',file_digest(root/'a/coupled-result.json'),context)
            (root/'a/coupled-result.json').write_text(json.dumps(first))
            # 관측 원문·결과 해시가 있어도 실행 INP가 결속된 강우와 다르면 거부한다.
            path = root/'a/network/network.inp'
            path.write_text(path.read_text().replace('S1 WL_AWS_G401','S1 G'))
            network['files']['network.inp'] = file_digest(path)
            (root/'a/network/network-result.json').write_text(json.dumps(network))
            changed = deepcopy(first)
            changed['files']['network/network.inp'] = file_digest(path)
            changed['files']['network/network-result.json'] = file_digest(root/'a/network/network-result.json')
            (root/'a/coupled-result.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(EvaluationError,'NETWORK_RAIN_INPUT_MISMATCH'):
                read_coupled_record(root/'a',file_digest(root/'a/coupled-result.json'),context)
            path.write_bytes((root/'b/network/network.inp').read_bytes())
            for name in ('network/network.inp','network/network.out','network-frames.jsonl','exchange-ledger.jsonl'):
                if (root/'a'/name).exists():
                    self.assertEqual((root/'a'/name).read_bytes(),(root/'b'/name).read_bytes())


if __name__ == '__main__':
    unittest.main()
