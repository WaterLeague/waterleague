"""PostgreSQL lease 큐. 작업마다 별도 프로세스·한정 경로·fencing 적용."""
import os,sys,time,json,subprocess,hashlib,signal
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from local_config import load
load()
os.umask(0o077)
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.queue import claim, finish, TABLES
from waterleague_sim.runtime import database_url
from waterleague_sim.shared_physics import run_once as run_shared_physics
from waterleague_sim.historical import process as process_historical
MODELS=read_catalog(ROOT/'data/models')
ARTIFACTS=Path(os.environ.get('ARTIFACTS_PATH',ROOT/'data/runs')).resolve()

def process(conn,job):
 if job['queue_kind'] not in TABLES:raise ValueError('지원하지 않는 계산 큐')
 if job['queue_kind']=='HISTORICAL':return process_historical(conn,job,ARTIFACTS)
 root=ARTIFACTS/'research-candidates' if job['queue_kind']=='RESEARCH_CANDIDATE' else ARTIFACTS
 path=root/str(job['id'])/str(job['lease_token']);path.mkdir(parents=True,exist_ok=False)
 model_bytes=MODELS.get(job['model_hash']);model_hash=hashlib.sha256(model_bytes).hexdigest() if model_bytes else None
 # Java가 정렬·직렬화한 원문 그대로 해시 비교한다.
 expected=hashlib.sha256((job['model_hash']+'\n'+job['placements']).encode()).hexdigest()
 state='REJECTED';error='INPUT_HASH_MISMATCH';result=None
 if expected==job['input_hash'] and model_hash==job['model_hash']:
  try:
   payload={'placements':json.loads(job['placements']),'modelHash':job['model_hash'],'inputHash':job['input_hash']}
  except (ValueError,TypeError):
   return finish(conn,job,'REJECTED',None,'INPUT_INVALID')
  (path/'request.json').write_text(json.dumps(payload,ensure_ascii=False));(path/'model-source.json').write_bytes(model_bytes)
  env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','SWMM_LIBRARY','SIMULATION_CACHE_PATH','SIMULATION_CACHE_ENABLED']};env['PYTHONPATH']=str(ROOT/'simulation')
  child=subprocess.Popen([sys.executable,'-m','waterleague_sim.run_job',str(path)],env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   code=child.wait(timeout=90)
   if code==0:
    result=json.loads((path/'result.json').read_text());result['artifactToken']=str(job['lease_token']);result['modelHash']=job['model_hash'];result['inputHash']=job['input_hash'];state='SUCCEEDED';error=None
   else:state='FAILED';error='SIMULATION_QUALITY_OR_ENGINE_FAILURE'
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGKILL);child.wait();state='FAILED';error='SIMULATION_TIMEOUT'
 saved=finish(conn,job,state,result,error)
 print('계산 작업',job['queue_kind'],job['id'],state if saved else 'LEASE_DISCARDED',flush=True)
 return saved

def main():
 with psycopg.connect(database_url(),autocommit=True,row_factory=dict_row) as conn:
  # SWMM은 프로세스별 전역 상태를 사용하므로 이 워커에서는 한 작업씩 실행한다.
  while True:
   job=claim(conn)
   if job:process(conn,job)
   shared=run_shared_physics(conn,ARTIFACTS)
   if '--once' in sys.argv:return
   if not job and not shared:time.sleep(2)
if __name__=='__main__':main()
