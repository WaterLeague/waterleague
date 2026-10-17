"""공통 로컬 환경으로 API·워커·프론트 실행."""
from local_config import ROOT,load
import os,sys,subprocess
from pathlib import Path
load()
mode=sys.argv[1] if len(sys.argv)>1 else ''
private_names={'DB_URL','DB_USER','DB_PASSWORD','DATABASE_URL','KMA_API_KEY','VWORLD_API_KEY','VWORLD_DOMAIN','MFA_ENCRYPTION_KEY'}
required_names={
 'api':{'DB_URL','DB_USER','DB_PASSWORD','MFA_ENCRYPTION_KEY','KMA_API_KEY'},
 'provision':{'DB_URL','DB_USER','DB_PASSWORD','MFA_ENCRYPTION_KEY'},
 'worker':{'DATABASE_URL','KMA_API_KEY'},
 'frontend':set(),
}
# 각 프로세스에 필요한 비밀 설정만 상속한다.
for name in private_names-required_names.get(mode,set()):os.environ.pop(name,None)
if mode in ['api','provision']:
 if not os.environ.get('DB_PASSWORD'):raise SystemExit('.env.local DB_PASSWORD 설정 필요')
 if not os.environ.get('JAVA_HOME') and sys.platform=='darwin':
  os.environ['JAVA_HOME']=subprocess.check_output(['/usr/libexec/java_home','-v','25'],text=True).strip()
 os.chdir(ROOT/'backend')
 if mode=='provision':
  java=Path(os.environ['JAVA_HOME'])/'bin/java';os.execv(str(java),[str(java),'-jar','target/waterleague-api-0.0.1-SNAPSHOT.jar','--spring.profiles.active=provision','--server.port=0'])
 os.execv('./mvnw',['./mvnw','spring-boot:run','-Dspring-boot.run.profiles=local'])
elif mode=='worker':
 os.chdir(ROOT);os.environ['PYTHONPATH']=str(ROOT/'simulation');python=ROOT/'simulation/.venv/bin/python';os.execv(str(python),[str(python),'-m','waterleague_sim.worker',*sys.argv[2:]])
elif mode=='frontend':
 os.chdir(ROOT/'frontend');os.execvp('pnpm',['pnpm','dev'])
else:raise SystemExit('사용법: python3 scripts/run_local.py api|worker|frontend|provision')
