"""직접 AWS 응답의 원문·시계·품질·중복 소유 및 네이티브 재현 검사."""
from copy import deepcopy
from importlib.util import find_spec
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.live_rainfall import METHOD, capture, sha
from waterleague_sim.forcing.observed_rainfall import compile_rainfall, utc
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.ingestion import live
from waterleague_sim.reference.flood_cases import mesh, coupled_case

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from run_live_surface import execute
START = utc('2022-08-08T10:46:00Z')
END = START + timedelta(minutes=2)


def response(station='421', end=END, *, start=START-timedelta(minutes=61)):
    # 단위 검사의 구간 분할 응답이며 운영 원본이나 새 관측으로 등록하지 않는다.
    source = ROOT/f'data/raw/kma-{station}-202208081800-202208082359.txt'
    lines = source.read_text().splitlines()
    raw = ('\n'.join(line for line in lines if line.startswith('#') or
        start <= datetime.strptime(line.split()[0], '%Y%m%d%H%M').replace(tzinfo=live.KST) <= end)+'\n').encode()
    meta = {'provider':'KMA_AWS_DIRECT', 'endpoint':live.ENDPOINT,
        'parameters':{'tm1':start.astimezone(live.KST).strftime('%Y%m%d%H%M'),
            'tm2':end.astimezone(live.KST).strftime('%Y%m%d%H%M'), 'stn':station, 'disp':'0', 'help':'1'},
        'fetchedAt':'2026-10-17T13:56:56.235988+00:00', 'sha256':sha(raw),
        'purpose':'SIMULATION_USED_INPUT_ONLY'}
    return {'rawUtf8':raw.decode(), 'metadata':meta}


def specification(model, end=END):
    return {'schemaVersion':2, 'sourceType':METHOD, 'startUtc':START.isoformat(), 'endUtc':end.isoformat(),
        'assignmentEvidence':'단위 검사 전용 합성 영역, 서울 배정 아님',
        'stationByTriangle':['421' if owner=='SURFACE' else None for owner in model['rainfallOwner']],
        'stations':[{'stationId':'421', 'responses':[response(end=end)]}]}


class LiveSurfaceTests(unittest.TestCase):
    def test_chunks_exactly_rebuild_same_observations_without_network(self):
        model = mesh(2, 2)
        one = specification(model)
        two = deepcopy(one)
        split = START-timedelta(minutes=20)
        two['stations'][0]['responses'] = [response(end=split), response(start=split)]
        with patch.object(live, 'fetch_range', side_effect=AssertionError('재생 네트워크 금지')):
            a, b = [compile_rainfall(v, model, 120) for v in (one, two)]
        self.assertEqual(a.events, b.events)
        self.assertEqual(a.summary['expectedSurfaceRainfallM3'], b.summary['expectedSurfaceRainfallM3'])
        self.assertGreater(a.summary['expectedSurfaceRainfallM3'], 0)
        self.assertFalse(a.summary['directResponse']['replayRequiresNetwork'])
        self.assertEqual(len(b.summary['stations'][0]['responseSha256']), 2)
        self.assertEqual(a.summary['stations'][0]['sourceHashKind'], 'STATION_DERIVATION_BUNDLE')

    def test_bad_source_metadata_hash_future_time_and_extra_fields_rejected(self):
        model = mesh(2, 2)
        for field, value in [('endpoint','https://example.com/'), ('sha256','0'*64),
                             ('fetchedAt','2020-01-01T00:00:00Z'), ('authKey','never-archive-this')]:
            spec = specification(model)
            spec['stations'][0]['responses'][0]['metadata'][field] = value
            with self.subTest(field=field), self.assertRaises(FloodModelError):
                compile_rainfall(spec, model, 120)
        spec = specification(model)
        spec['stations'][0]['responses'][0]['metadata']['parameters']['authKey'] = 'forbidden'
        with self.assertRaises(FloodModelError):
            compile_rainfall(spec, model, 120)

    def test_missing_minute_not_filled_and_changed_overlap_rejected_even_with_new_hash(self):
        model = mesh(2, 2)
        spec = specification(model)
        row = spec['stations'][0]['responses'][0]
        row['rawUtf8'] = '\n'.join(line for line in row['rawUtf8'].splitlines()
                                   if not line.startswith('202208081947'))+'\n'
        row['metadata']['sha256'] = sha(row['rawUtf8'].encode())
        with self.assertRaisesRegex(FloodModelError, 'RAIN_QUALITY_INVALID'):
            compile_rainfall(spec, model, 120)
        spec = specification(model)
        split = START-timedelta(minutes=20)
        spec['stations'][0]['responses'] = [response(end=split), response(start=split)]
        row = spec['stations'][0]['responses'][1]
        lines = row['rawUtf8'].splitlines()
        index = next(i for i, line in enumerate(lines) if not line.startswith('#'))
        fields = lines[index].split(); fields[8] = '20.0'; lines[index] = ' '.join(fields)
        row['rawUtf8'] = '\n'.join(lines)+'\n'
        row['metadata']['sha256'] = sha(row['rawUtf8'].encode())
        with self.assertRaisesRegex(FloodModelError, 'OVERLAPPING_RESPONSE_CHANGED'):
            compile_rainfall(spec, model, 120)

    def test_network_owned_area_and_schema_mismatch_rejected_before_capture(self):
        model = mesh(2, 2); model['rainfallOwner'][0] = 'NETWORK'
        spec = specification(model)
        result = compile_rainfall(spec, model, 120)
        self.assertEqual(result.summary['stations'][0]['surfaceAreaM2'], 87.5)
        with patch.object(live, 'observed_forcing') as fetch:
            with self.assertRaisesRegex(FloodModelError, 'ASSIGNMENT_INVALID'):
                capture(model, ['421']*8, START, END, 'secret', 'TEST')
            fetch.assert_not_called()
        spec['schemaVersion'] = 1
        with self.assertRaisesRegex(FloodModelError, 'REFERENCE_INVALID'):
            compile_rainfall(spec, model, 120)

    def test_capture_deduplicates_stations_and_never_embeds_credentials(self):
        model = mesh(2, 2)
        row = response()
        with patch.object(live, 'observed_forcing', return_value=({}, [
                (row['rawUtf8'].encode(), row['metadata'])])) as fetch:
            result = capture(model, ['421']*8, START, END, 'private-key', 'TEST ONLY')
        fetch.assert_called_once_with('421', START, END, 'private-key')
        self.assertNotIn('private-key', json.dumps(result))
        self.assertEqual(result, specification(model) | {'assignmentEvidence':'TEST ONLY'})

    def test_live_entry_refuses_existing_output_and_conflicting_clock_before_api(self):
        model = mesh(2, 2)
        request = {'mode':'surface', 'model':model, 'rainfall':{k:v for k,v in specification(model).items()
            if k in ('startUtc','endUtc','stationByTriangle','assignmentEvidence')}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(live, 'observed_forcing') as fetch:
            with self.assertRaisesRegex(FloodModelError, 'OUTPUT_EXISTS'):
                execute(request, Path(temporary), 'private-key')
            request['model']['startUtc'] = '2022-08-08T00:00:00Z'
            with self.assertRaisesRegex(FloodModelError, 'CLOCK_MISMATCH'):
                execute(request, Path(temporary)/'not-created', 'private-key')
            fetch.assert_not_called()
            self.assertFalse((Path(temporary)/'not-created').exists())

    def test_live_coupled_entry_does_not_override_existing_forcing(self):
        model = coupled_case()
        request = {'mode':'coupled','model':model,'rainfall':{k:v for k,v in specification(model['surface']).items()
            if k in ('startUtc','endUtc','stationByTriangle','assignmentEvidence')}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(live, 'observed_forcing') as fetch:
            for key in ('initialization','observedRainfall','surfaceRainfall','networkRainfallTriangles'):
                value = deepcopy(request); value['model'][key] = {'test':'not-replaceable'}
                with self.subTest(key=key), self.assertRaisesRegex(FloodModelError, 'FORCING_CONFLICT'):
                    execute(value, Path(temporary)/key, 'private-key')
            fetch.assert_not_called()

    def test_acquisition_resource_limit_rejects_without_queries_or_resolution_changes(self):
        model = mesh(2, 2)
        assignments = ['421','401','108','421','401','108','421','401']
        with patch.object(live, 'observed_forcing') as fetch:
            with self.assertRaisesRegex(FloodModelError, 'ACQUISITION_LIMIT'):
                capture(model, assignments, START, START+timedelta(days=29), 'secret', 'TEST')
            fetch.assert_not_called()
        self.assertEqual(model['maxStepSeconds'], 1.)
        self.assertEqual(len(model['triangles']), 8)

    @unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
    def test_real_engines_preserve_frames_exchange_and_offline_replay(self):
        model = mesh(2, 2)
        model.update(schemaVersion=2, maxStepSeconds=.1, startUtc=START.isoformat(),
            durationSeconds=120, frameOutput={'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64',
                'maxFrames':20, 'maxBytes':1024**2})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(live, 'fetch_range', side_effect=AssertionError('재생 네트워크 금지')):
                a = run_observed_surface(model, specification(model), root/'a')
                saved = json.loads((root/'a/observed-surface-input.json').read_text())
                b = run_observed_surface(saved['surface'], saved['observedRainfall'], root/'b')
            self.assertEqual(a['final'], b['final'])
            self.assertEqual(a['numericalStatus'], 'PASSED')
            for path in (root/'a/surface/native-frames').glob('*'):
                self.assertEqual(path.read_bytes(), (root/'b/surface/native-frames'/path.name).read_bytes())
            self.assertAlmostEqual(a['final']['storageM3'], a['observedRainfall']['expectedSurfaceRainfallM3'])
            coupled = coupled_case(initial_network=0, exchange_ms=500)
            coupled['surface']['schemaVersion'] = 2
            text = coupled['network']['inputText'].replace('01/01/2020','08/08/2022')
            text = text.replace('00:00:00','10:46:00').replace('00:02:01','10:48:01')
            coupled['network'].update(inputText=text, timeZone='UTC')
            coupled['observedRainfall'] = specification(coupled['surface'])
            value = run_coupled(coupled, root/'coupled')
            self.assertEqual(value['numericalStatus'], 'PASSED')
            self.assertGreater(value['balance']['surfaceToNetworkM3'], 0)
            self.assertLess(abs(value['balance']['balanceResidualM3']), 1e-5)


if __name__ == '__main__':
    unittest.main()
