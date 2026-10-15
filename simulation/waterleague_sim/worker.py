"""PostgreSQL lease 큐. 작업마다 별도 프로세스·한정 경로·fencing 적용."""
import os,sys,time,json,uuid,subprocess,hashlib,signal
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from local_config import load
load()
os.umask(0o077)
MODEL_PATH=ROOT/'data/models/seongsu-lab.json'
ARTIFACTS=Path(os.environ.get('ARTIFACTS_PATH',ROOT/'data/runs')).resolve()

def claim(conn):
 with conn.transaction():
  conn.execute("UPDATE simulation_jobs SET state='FAILED',error_code='WORKER_RETRY_EXHAUSTED',finished_at=now() WHERE state='RUNNING' AND lease_until<now() AND attempts>=3")
  job=conn.execute("SELECT j.*,v.placements FROM simulation_jobs j JOIN strategy_versions v ON v.id=j.version_id WHERE (j.state='QUEUED' OR (j.state='RUNNING' AND j.lease_until<now())) AND j.attempts<3 ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1").fetchone()
  if not job:return None
  token=uuid.uuid4();conn.execute("UPDATE simulation_jobs SET state='RUNNING',attempts=attempts+1,lease_token=%s,lease_until=now()+interval '180 seconds' WHERE id=%s",(token,job['id']))
  return job|{'lease_token':token}

def process(conn,job):
 path=ARTIFACTS/str(job['id'])/str(job['lease_token']);path.mkdir(parents=True,exist_ok=False)
 model_bytes=MODEL_PATH.read_bytes();model_hash=hashlib.sha256(model_bytes).hexdigest()
 payload={'placements':json.loads(job['placements']),'modelHash':job['model_hash'],'inputHash':job['input_hash']}
 # Java가 정렬·직렬화한 원문 그대로 해시 비교한다.
 expected=hashlib.sha256((job['model_hash']+'\n'+job['placements']).encode()).hexdigest()
 state='REJECTED';error='INPUT_HASH_MISMATCH';result=None
 if expected==job['input_hash'] and model_hash==job['model_hash']:
  (path/'request.json').write_text(json.dumps(payload,ensure_ascii=False));(path/'model-source.json').write_bytes(model_bytes)
  env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','SWMM_LIBRARY']};env['PYTHONPATH']=str(ROOT/'simulation')
  child=subprocess.Popen([sys.executable,'-m','waterleague_sim.run_job',str(path)],env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   code=child.wait(timeout=90)
   if code==0:
    result=json.loads((path/'result.json').read_text());result['artifactToken']=str(job['lease_token']);result['modelHash']=job['model_hash'];result['inputHash']=job['input_hash'];state='SUCCEEDED';error=None
   else:state='FAILED';error='SIMULATION_QUALITY_OR_ENGINE_FAILURE'
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGKILL);child.wait();state='FAILED';error='SIMULATION_TIMEOUT'
 with conn.transaction():
  # 만료된 워커는 새 lease의 결과를 덮어쓸 수 없다.
  conn.execute("UPDATE simulation_jobs SET state=%s,result=%s,error_code=%s,finished_at=now(),lease_until=NULL WHERE id=%s AND state='RUNNING' AND lease_token=%s AND lease_until>now()",(state,json.dumps(result,ensure_ascii=False,allow_nan=False) if result else None,error,job['id'],job['lease_token']))
 print('계산 작업',job['id'],state,flush=True)

def main():
 with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row) as conn:
  # SWMM은 프로세스별 전역 상태를 사용하므로 이 워커에서는 한 작업씩 실행한다.
  while True:
   job=claim(conn)
   if job:process(conn,job)
   elif '--once' in sys.argv:return
   else:time.sleep(2)
if __name__=='__main__':main()
