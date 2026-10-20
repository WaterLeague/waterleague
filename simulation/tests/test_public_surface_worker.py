"""공개 워커의 동시 게시·재시작·실패 철회. 정책 fixture는 운영 목록에 등록하지 않는다."""
from copy import deepcopy
from datetime import timedelta
from importlib.util import find_spec
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.forcing.live_rainfall import extend, read_live_station
from waterleague_sim.ingestion import live
from waterleague_sim.public_surface import repository as repo, service
from waterleague_sim.public_surface.recipe import request, POLICY
from waterleague_sim.public_surface.run_job import execute
from waterleague_sim import job_runtime
from simulation.tests.test_live_surface_rainfall import START, END, response, specification
from simulation.tests.test_live_network_rainfall import case


def fixture():
    model=case();model.pop('observedRainfall')
    start=START-timedelta(days=7)
    model['network']['inputText']=model['network']['inputText'].replace('08/08/2022','08/01/2022')
    model['evidence']=model['surface']['evidence']=repo.CLASSIFICATION
    model['surface']['terrainProvenance']={'absoluteVerticalReferenceVerified':True}
    model['surface']['frameOutput']={'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64','maxFrames':10000,'maxBytes':1024**2}
    rainfall={k:v for k,v in specification(model['surface']).items() if k in ('stationByTriangle','assignmentEvidence')}
    rainfall['stationByCatchment']={'S1':'421'}
    return {'schemaVersion':1,'statePolicy':POLICY,'startUtc':start.isoformat(),
        'evaluationStartUtc':START.isoformat(),'endBeforeUtc':(START+timedelta(days=7)).isoformat(),
        'model':model,'rainfall':rainfall}


def policy_bundle(root):
    recipe=fixture()
    numerical={'schemaVersion':1,'modelTemplateSha256':repo.sha(repo.encode(recipe['model'])),
               'engineSha256':'0'*64}
    evidence={'schemaVersion':1,'classification':repo.CLASSIFICATION,
        'modelTemplateSha256':numerical['modelTemplateSha256'],'startUtc':recipe['startUtc'],
        'evaluationStartUtc':recipe['evaluationStartUtc'],
        'references':{k:'fixture-evidence.txt' for k in ('horizontalReference','verticalReference','terrain',
            'network','assets','externalBoundaries','dryWetInitializationComparison','longerWarmupComparison')}}
    contents={'recipe.json':repo.encode(recipe),'numerical-policy.json':repo.encode(numerical),
        'input-evidence.json':repo.encode(evidence),'fixture-evidence.txt':b'TEST FIXTURE ONLY. NOT PUBLIC DATA OR FIELD EVIDENCE.\n'}
    manifest={'schemaVersion':1,'files':{k:repo.sha(v) for k,v in contents.items()}}
    raw=repo.encode(manifest);digest=repo.sha(raw);folder=root/digest;folder.mkdir(parents=True)
    for name,body in contents.items():(folder/name).write_bytes(body)
    (folder/'manifest.json').write_bytes(raw)
    model={'id':'fixture-only','name':'게시 계약 시험 전용','inputBundleSha256':digest,
           'numericalPolicySha256':manifest['files']['numerical-policy.json'],
           'classification':repo.CLASSIFICATION,'bounds':[-100,-100,100,100]}
    return model,folder,manifest,recipe


class PublicSurfaceWorkerTests(unittest.TestCase):
    def test_snapshot_freezes_current_native_map_and_rejects_modified_copy(self):
        raw, city = repo.city_source(repo.ROOT)
        frontend = (repo.ROOT/'frontend/src/domains/city/repository/cityRepository.ts').read_text()
        self.assertIn(f"export const CITY_HASH = '{repo.CITY_SHA256}'", frontend)
        self.assertIn("export const CITY_PATH = '/data/seoul-native-v1/city.json'", frontend)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            _, bundle, manifest, _ = policy_bundle(root/'bundles')
            local = root/'checkout'
            current = local/repo.CITY_FILE
            current.parent.mkdir(parents=True)
            current.write_bytes(raw)
            old = local/'frontend/public/data/seoul-v1/city.json'
            old.parent.mkdir(parents=True)
            old.write_bytes(b'{"coordinateSystem":"EPSG:5186","originProjected":[198128,551989]}')
            directory = root/'run'
            directory.mkdir()
            with patch.object(repo, 'ROOT', local):
                service.snapshot(directory, bundle, manifest)
            saved = directory/'source'/repo.CITY_FILE
            self.assertEqual(saved.read_bytes(), raw)
            self.assertEqual(repo.city_source(directory/'source')[1], city)
            self.assertFalse((directory/'source/frontend/public/data/seoul-v1/city.json').exists())
            saved.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(FloodModelError, 'HASH_OR_SIZE_MISMATCH'):
                repo.city_source(directory/'source')
            current.write_bytes(raw+b'\n')
            next_run = root/'next-run'
            next_run.mkdir()
            with patch.object(repo, 'ROOT', local), self.assertRaisesRegex(
                    FloodModelError, 'HASH_OR_SIZE_MISMATCH'):
                service.snapshot(next_run, bundle, manifest)
            self.assertEqual(list(next_run.iterdir()), [])

    def test_missing_current_map_never_falls_back_to_legacy_or_starts_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            model, bundle, manifest, recipe = policy_bundle(root/'bundles')
            local = root/'checkout'
            old = local/'frontend/public/data/seoul-v1/city.json'
            old.parent.mkdir(parents=True)
            old.write_bytes(b'{"coordinateSystem":"EPSG:5186","originProjected":[198128,551989]}')
            artifacts = root/'artifacts'
            with patch.object(repo, 'ROOT', local), patch.object(repo, 'load_registry',
                    return_value={model['id']: model}), patch.object(repo, 'load_bundle',
                    return_value=(bundle, manifest, recipe)), patch.object(service, 'run_engine') as run:
                self.assertTrue(service.run_once(artifacts, clock=lambda: END+timedelta(minutes=2)))
            run.assert_not_called()
            state = repo.decode(repo.read(artifacts/'public-surface/state/fixture-only.json'))
            self.assertEqual(state['status'], 'FAILED')
            self.assertEqual(state['errorCode'], 'PUBLIC_SURFACE_MAP_UNAVAILABLE')
            self.assertEqual(repo.decode(repo.read(artifacts/'public-surface/current.json'))['runs'], [])
            self.assertEqual(repo.load_registry(), {})

    def test_research_cistern_does_not_become_public_baseline(self):
        value = fixture()
        value['model']['connectedCisternDesign'] = {'schemaVersion': 1}
        with self.assertRaisesRegex(FloodModelError, 'PUBLIC_SURFACE_FORCING_COMPOSITION_UNSUPPORTED'):
            request(value, END)

    def test_registry_rejects_invalid_geography_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();model,*_=policy_bundle(root/'bundles')
            path=root/'registry.json'
            for field,value in [('id',None),('name',''),('bounds',[0,0,0,1]),
                                ('bounds',[0,0,True,1]),('bounds',[-60001,0,1,1]),('inputBundleSha256',12)]:
                raw=repo.encode({'schemaVersion':1,'scope':'PUBLIC_CURRENT_BASELINE_ONLY',
                                 'models':[model | {field:value}]})
                path.write_bytes(raw)
                with self.subTest(field=field,value=value),self.assertRaisesRegex(FloodModelError,'REGISTRY_INVALID'):
                    repo.load_registry(path,repo.sha(raw))

    def test_native_timeout_kills_process_group_without_publishing(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(job_runtime.subprocess,'Popen') as popen,patch.object(
                job_runtime.os,'killpg') as kill, patch.object(job_runtime.time,'monotonic',side_effect=[0,0,121]):
            child=popen.return_value;child.pid=123456
            child.wait.side_effect=[subprocess.TimeoutExpired('native',120),-9]
            with self.assertRaisesRegex(FloodModelError,'CALCULATION_TIMEOUT'):
                service.run_engine(Path(temp).resolve())
            kill.assert_called_once_with(child.pid,job_runtime.signal.SIGKILL)
            self.assertEqual(list(Path(temp).iterdir()),[])
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertNotIn('DB_PASSWORD',popen.call_args.kwargs['env'])

    def test_production_registry_is_empty_and_does_not_fetch_or_create_results(self):
        self.assertEqual(repo.load_registry(),{})
        with tempfile.TemporaryDirectory() as temp,patch.object(live,'fetch_range') as fetch:
            path=Path(temp).resolve()/'not-created'
            self.assertFalse(service.run_once(path))
            self.assertFalse(path.exists());fetch.assert_not_called()

    def test_recipe_extends_clock_but_keeps_origin_physics_and_excludes_warmup(self):
        original=fixture();copy=deepcopy(original)
        a,b=[request(original,end) for end in (END,END+timedelta(minutes=1))]
        self.assertEqual(original,copy)
        self.assertEqual(a['model']['evaluationMetrics']['startMilliseconds'],7*86400*1000)
        self.assertEqual(a['model']['durationSeconds'],7*86400+120)
        self.assertIn('END_TIME 10:48:01',a['model']['network']['inputText'])
        self.assertIn('END_TIME 10:49:01',b['model']['network']['inputText'])
        for key in ('verticesM','triangles','initialDepthM','manningN','maxStepSeconds','rainfallOwner'):
            self.assertEqual(a['model']['surface'][key],b['model']['surface'][key])
        with self.assertRaisesRegex(FloodModelError,'WINDOW_INVALID'):
            request(original,START-timedelta(minutes=1))

    def test_bundle_source_and_policy_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();model,folder,_,_=policy_bundle(root)
            self.assertEqual(repo.load_bundle(model,root)[0],folder)
            (folder/'fixture-evidence.txt').write_text('changed')
            with self.assertRaisesRegex(FloodModelError,'HASH_OR_SIZE'):
                repo.load_bundle(model,root)
            for name in ('../escape','/absolute',''):
                with self.assertRaises(FloodModelError):repo.safe_path(root,name)
            (root/'alias').symlink_to(root)
            with self.assertRaises(FloodModelError):repo.safe_path(root,'alias/manifest.json')
            with self.assertRaises(FloodModelError):repo.decode(b'{"x":1,"x":2}')
            with self.assertRaises(FloodModelError):repo.decode(b'{"x":NaN}')

    def test_incremental_capture_queries_only_tail_and_preserves_old_raw(self):
        model=case()['surface'];previous=specification(model);saved=deepcopy(previous)
        end=END+timedelta(minutes=1);tail=response(start=END,end=end)
        with patch.object(live,'fetch_range',return_value=(tail['rawUtf8'].encode(),tail['metadata'])) as fetch:
            extended=extend(previous,end,'private-key')
        fetch.assert_called_once_with('421',END,end,'private-key')
        self.assertEqual(previous,saved)
        self.assertEqual(extended['stations'][0]['responses'][0],saved['stations'][0]['responses'][0])
        self.assertNotIn('private-key',json.dumps(extended))
        data,_=read_live_station(extended['stations'][0],START,end)
        self.assertEqual(len(data['depthsMm']),3)
        row=tail['rawUtf8'].splitlines()
        index=next(i for i,line in enumerate(row) if not line.startswith('#'))
        fields=row[index].split();fields[8]='25.0';row[index]=' '.join(fields)
        body=('\n'.join(row)+'\n').encode();metadata=tail['metadata'] | {'sha256':repo.sha(body)}
        with patch.object(live,'fetch_range',return_value=(body,metadata)):
            with self.assertRaisesRegex(FloodModelError,'OVERLAPPING_RESPONSE_CHANGED'):
                extend(previous,end,'private-key')

    def test_more_than_32_saved_minute_responses_replay_with_same_values(self):
        reference={'stationId':'421','responses':[]}
        cursor=START-timedelta(minutes=61)
        while cursor<END:
            reference['responses'].append(response(start=cursor,end=cursor+timedelta(minutes=1)))
            cursor+=timedelta(minutes=1)
        first,_=read_live_station(reference,START,END)
        second,_=read_live_station({'stationId':'421','responses':[response()]},START,END)
        self.assertEqual(first['observations'],second['observations'])
        self.assertEqual(len(reference['responses']),63)

    def test_lock_prevents_parallel_attempt_and_atomic_index_preserves_other_basin(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();clock=END+timedelta(minutes=2)
            model={'id':'a'};models={'a':model,'b':{'id':'b'}}
            row={'basinId':'a','lastFrameAt':END.isoformat()}
            other={'basinId':'b','lastFrameAt':END.isoformat()}
            path=root/'public-surface/current.json'
            repo.atomic_json(path,{'schemaVersion':1,'runs':[other]})
            service.index_update(root,model,row,models,clock)
            self.assertEqual(len(repo.decode(repo.read(path))['runs']),2)
            service.index_update(root,model,None,models,clock)
            self.assertEqual(repo.decode(repo.read(path))['runs'],[other])
            with repo.locked(root/'test.lock') as a,repo.locked(root/'test.lock') as b:
                self.assertTrue(a);self.assertFalse(b)
            with self.assertRaisesRegex(FloodModelError,'RESULT_EXPIRED'):
                service.index_update(root,model,row,models,clock+timedelta(minutes=4))

    def test_worker_restart_lineage_failure_withdrawal_and_no_repeat_same_minute(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();model,folder,manifest,recipe=policy_bundle(root/'bundles')
            artifacts=root/'artifacts';at=[END+timedelta(minutes=2)]; seen=[]
            def snapshot(directory,*_):
                (directory/'source').mkdir()
            def run(directory):
                previous=directory/'previous-input.json'
                seen.append(repo.decode(repo.read(previous)) if previous.exists() else None)
                (directory/'calculation').mkdir()
                repo.atomic_json(directory/'calculation/coupled-input.json',{'fixture':'TEST_ONLY','sequence':len(seen)})
            def publish(_model,directory,identifier,token,cutoff,clock):
                return {'id':str(identifier),'token':str(token),'basinId':model['id'],
                    'inputBundleSha256':model['inputBundleSha256'],'numericalPolicySha256':model['numericalPolicySha256'],
                    'lastFrameAt':cutoff.isoformat()}
            with patch.object(repo,'load_registry',return_value={model['id']:model}),patch.object(repo,'load_bundle',
                    return_value=(folder,manifest,recipe)),patch.object(service,'snapshot',side_effect=snapshot),patch.object(
                    service,'run_engine',side_effect=run) as engine,patch.object(service,'publication',side_effect=publish):
                self.assertTrue(service.run_once(artifacts,clock=lambda:at[0]))
                self.assertFalse(service.run_once(artifacts,clock=lambda:at[0]));self.assertEqual(engine.call_count,1)
                state=artifacts/'public-surface/state/fixture-only.json'
                # 게시 직후 상태 파일 저장 전에 종료된 경우 인덱스의 원 묶음으로 복구한다.
                repo.atomic_json(state,{'status':'RUNNING','attemptedThrough':END.isoformat()})
                at[0]+=timedelta(minutes=1)
                self.assertTrue(service.run_once(artifacts,clock=lambda:at[0]))
                self.assertEqual(seen,[None,{'fixture':'TEST_ONLY','sequence':1}])
                before=repo.decode(repo.read(state))['previous']
                engine.side_effect=FloodModelError('TEST_FAILURE');at[0]+=timedelta(minutes=1)
                self.assertTrue(service.run_once(artifacts,clock=lambda:at[0]))
                self.assertEqual(repo.decode(repo.read(artifacts/'public-surface/current.json'))['runs'],[])
                self.assertEqual(repo.decode(repo.read(state))['previous'],before)
                self.assertEqual(len(list((artifacts/'public-surface').glob('*/*/failure.json'))),1)

    @unittest.skipUnless(find_spec('anuga'),'flood 선택 의존성 설치 필요')
    def test_publication_contract_fixture_verifies_native_results_and_rejects_tampering(self):
        # 등록 승인 계약을 시험하는 임시 자료이며 실제 서울 공개 모형으로 등록하지 않는다.
        from pyproj import CRS
        from waterleague_sim.terrain.grid import digest
        from waterleague_sim.engine.coupled_flood import run_coupled
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp).resolve()
            model=case();spec=model.pop('observedRainfall')
            model['evidence']=model['surface']['evidence']=repo.CLASSIFICATION
            terrain={'coordinateWkt':CRS('EPSG:5186').to_wkt(),'originProjected':[198128.,551989.],
                     'absoluteVerticalReferenceVerified':True,
                     'limitations':['TEST FIXTURE ONLY. NOT SEOUL TERRAIN OR FIELD EVIDENCE.']}
            coordinate='SOURCE_PROJECTED_LOCAL:'+digest(terrain)
            model['coordinateSystem']=model['network']['coordinateSystem']=coordinate
            model['surface'].update(coordinateSystem=coordinate,terrainProvenance=terrain,startUtc=START.isoformat(),
                frameOutput={'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64','maxFrames':1000,'maxBytes':16*1024**2})
            rainfall={k:v for k,v in spec.items() if k in ('startUtc','endUtc','stationByTriangle',
                                                         'stationByCatchment','assignmentEvidence')}
            repo.atomic_json(directory/'request.json',{'model':model,'rainfall':rainfall})
            result=run_coupled(model | {'observedRainfall':spec},directory/'calculation')
            network=repo.decode(repo.read(directory/'calculation/network/network-result.json'))
            surface=repo.decode(repo.read(directory/'calculation/surface/surface-result.json'))
            policy={'schemaVersion':1,'engineSha256':service.engine_signature(network,surface,result)}
            repo.atomic_json(directory/'input-bundle/numerical-policy.json',policy)
            city_raw, _ = repo.city_source(repo.ROOT)
            city_path = directory/'source'/repo.CITY_FILE
            city_path.parent.mkdir(parents=True)
            city_path.write_bytes(city_raw)
            registered={'id':'test-only-unregistered','classification':repo.CLASSIFICATION,'bounds':[-100,-100,100,100],
                'inputBundleSha256':'0'*64,'numericalPolicySha256':repo.sha(repo.encode(policy))}
            identifier,token=uuid.uuid4(),uuid.uuid4()
            row=service.publication(registered,directory,identifier,token,END,END+timedelta(minutes=2))
            self.assertEqual(row['forcingSource'],'OFFICIAL_OBSERVATIONS')
            self.assertEqual(row['lastFrameAt'],END.isoformat())
            catalog=repo.decode(repo.read(directory/'surface-playback/catalog.json',expected=row['catalogSha256']))
            for frame in catalog['frames']:
                self.assertEqual(repo.read(directory/'surface-playback'/frame['file']),
                                 repo.read(directory/'calculation/surface/native-frames'/frame['file']))
            shutil.rmtree(directory/'surface-playback')
            city_path.write_bytes(city_raw+b'\n')
            with self.assertRaisesRegex(FloodModelError, 'HASH_OR_SIZE_MISMATCH'):
                service.publication(registered,directory,identifier,token,END,END+timedelta(minutes=2))
            self.assertFalse((directory/'surface-playback').exists())
            city_path.write_bytes(city_raw)
            with self.assertRaisesRegex(FloodModelError,'EXPIRED_OR_UNBOUND'):
                service.publication(registered,directory,identifier,token,END,END+timedelta(minutes=6))
            path=directory/'calculation/network/network.inp';raw=repo.read(path)
            path.write_bytes(raw+b'\n; MODIFIED TEST INPUT\n')
            with self.assertRaisesRegex(FloodModelError,'RESULT_INTEGRITY_FAILED'):
                service.publication(registered,directory,identifier,token,END,END)
            path.write_bytes(raw)
            payload=repo.decode(repo.read(directory/'request.json'));payload['model']['durationSeconds']+=1
            repo.atomic_json(directory/'request.json',payload)
            with self.assertRaisesRegex(FloodModelError,'RESULT_INPUT_MISMATCH'):
                service.publication(registered,directory,identifier,token,END,END)
            self.assertEqual(repo.load_registry(),{})

    def test_corrupt_restart_state_does_not_reset_origin_or_start_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();model,*_=policy_bundle(root/'bundles')
            state=root/'artifacts/public-surface/state/fixture-only.json'
            state.parent.mkdir(parents=True);raw=b'{broken saved state';state.write_bytes(raw)
            with patch.object(repo,'load_registry',return_value={model['id']:model}),patch.object(service,'run_engine') as run:
                self.assertFalse(service.run_once(root/'artifacts',clock=lambda:END+timedelta(minutes=2)))
                run.assert_not_called()
            self.assertEqual(state.read_bytes(),raw)
            self.assertEqual(repo.decode(repo.read(state.with_name('fixture-only.failure.json')))['errorCode'],
                             'PUBLIC_SURFACE_STATE_RECOVERY_FAILED')

    @unittest.skipUnless(find_spec('anuga'),'flood 선택 의존성 설치 필요')
    def test_native_extension_preserves_earlier_water_state_and_offline_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            if os.environ.get('PUBLIC_SURFACE_EVIDENCE_DIR'):
                root=Path(os.environ['PUBLIC_SURFACE_EVIDENCE_DIR']).resolve()
                self.assertFalse(root.exists());root.mkdir(parents=True)
            model=case();spec=model.pop('observedRainfall')
            model['surface']['frameOutput']={'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64',
                'maxFrames':1000,'maxBytes':16*1024**2}
            model['frameIntervalMilliseconds']=60000
            rainfall={k:v for k,v in spec.items() if k in ('startUtc','endUtc','stationByTriangle',
                                                         'stationByCatchment','assignmentEvidence')}
            first=root/'first';first.mkdir()
            repo.atomic_json(first/'request.json',{'model':model,'rainfall':rainfall})
            with patch('waterleague_sim.public_surface.run_job.capture',return_value=spec):
                result=execute(first,'TEST-KEY-NOT-REAL')
            self.assertEqual(result['numericalStatus'],'PASSED')
            old_raw=repo.read(first/'calculation/coupled-input.json')
            second=root/'extended';second.mkdir()
            (second/'previous-input.json').write_bytes(old_raw)
            longer=deepcopy(model)
            longer['network']['inputText']=longer['network']['inputText'].replace('10:48:01','10:49:01')
            longer['durationSeconds']=180
            longer['evaluationMetrics']['endMilliseconds']=180000
            end=END+timedelta(minutes=1)
            longer['surface']['durationSeconds']=180
            repo.atomic_json(second/'request.json',{'model':longer,'rainfall':rainfall | {'endUtc':end.isoformat()}})
            def fetch(station,start,stop,key):
                self.assertEqual((start,stop),(END,end))
                r=response(station,start=start,end=stop)
                return r['rawUtf8'].encode(),r['metadata']
            with patch.object(live,'fetch_range',side_effect=fetch) as fetched:
                extended=execute(second,'TEST-KEY-NOT-REAL')
            self.assertEqual(fetched.call_count,2)
            self.assertEqual(extended['numericalStatus'],'PASSED')
            self.assertEqual(repo.read(first/'calculation/coupled-input.json'),old_raw)
            a,b=[repo.decode(repo.read(d/'calculation/surface/native-frames/catalog.json')) for d in (first,second)]
            self.assertEqual(a['frames'],b['frames'][:len(a['frames'])])
            for frame in a['frames']:
                self.assertEqual(repo.read(first/'calculation/surface/native-frames'/frame['file']),
                                 repo.read(second/'calculation/surface/native-frames'/frame['file']))
            prefix={}
            for name in ('network-frames.jsonl','exchange-ledger.jsonl'):
                before=repo.read(first/'calculation'/name)
                self.assertTrue(repo.read(second/'calculation'/name).startswith(before),name)
                prefix[name]=repo.sha(before)
            saved=repo.decode(repo.read(second/'calculation/coupled-input.json'))
            for old,new in zip(spec['stations'],saved['observedRainfall']['stations']):
                self.assertEqual(new['responses'][:len(old['responses'])],old['responses'])
            from waterleague_sim.engine.coupled_flood import run_coupled
            with patch.object(live,'fetch_range',side_effect=AssertionError('재생 API 호출 금지')):
                replay=run_coupled(saved,root/'replay')
            self.assertEqual(extended['balance'],replay['balance'])
            self.assertEqual(extended['networkRainfall'],replay['networkRainfall'])
            from scripts.verify_live_network import compared
            matches=compared(second/'calculation',root/'replay')
            with self.assertRaisesRegex(FloodModelError,'PUBLIC_SURFACE_RESULT_INVALID'):
                service.publication({},second,uuid.uuid4(),uuid.uuid4(),end,end)
            self.assertGreater(extended['networkRainfall']['appliedCombinedRainfallM3'],0)
            self.assertGreater(b['frames'][-1]['storageM3'],0)
            proof={'classification':'NUMERICAL_EXTENSION_TEST_ONLY','rankingEligible':False,
                'publiclyPublished':False,'warmupDays':0,'testOnlySplitResponses':True,
                'matchedPrefixFrames':len(a['frames']),'matchedPrefixLedgers':prefix,
                'matchedReplayFiles':matches,'networkRainfall':extended['networkRainfall'],
                'limitations':['합성 관망·지형, 운영 공개 모형 아님',
                    '원문을 잘라 구성한 단위 검사 응답, 새 공식 조회 원문 아님',
                    '선행 7일 운영 수렴·장기 주 경계·네이티브 상태 체크포인트 검사와 구분']}
            repo.atomic_json(root/'verification.json',proof)
            if os.environ.get('PUBLIC_SURFACE_EVIDENCE_DIR'):
                sources=list((repo.ROOT/'simulation/waterleague_sim').rglob('*.py'))
                sources+=list((repo.ROOT/'simulation/native').glob('*.inc'))
                sources+=list((repo.ROOT/'tmp/network-rainfall-swmm-build/install/bin').glob('*'))
                sources+=[Path(__file__).resolve(),repo.ROOT/'scripts/verify_live_network.py',
                    repo.ROOT/'scripts/run_public_surface.py',repo.ROOT/'scripts/replay_coupled_bundle.py',
                    repo.ROOT/'scripts/build_rainfall_swmm.py',repo.ROOT/'scripts/build_network_swmm.py',
                    repo.ROOT/'scripts/build_live_swmm.py',repo.ROOT/'data/manifests/anuga-4.0.1.json',
                    repo.ROOT/'simulation/tests/test_live_network_rainfall.py',repo.ROOT/'simulation/tests/test_live_surface_rainfall.py',
                    repo.ROOT/'simulation/uv.lock',repo.ROOT/'simulation/pyproject.toml']
                for station in ('401','421'):
                    sources.append(repo.ROOT/f'data/raw/kma-{station}-202208081800-202208082359.txt')
                    sources.append(repo.ROOT/f'data/manifests/kma-{station}-202208081800-202208082359.json')
                for source in sources:
                    if source.is_file():
                        target=root/'source'/source.relative_to(repo.ROOT)
                        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                repo.atomic_json(root/'manifest.json',{'classification':proof['classification'],
                    'files':{str(p.relative_to(root)):repo.sha(repo.read(p)) for p in sorted(root.rglob('*')) if p.is_file()}})


if __name__=='__main__':unittest.main()
