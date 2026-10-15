"""공통 로컬 환경으로 API·워커·프론트 실행."""
from local_config import ROOT,load
import os,sys,subprocess
load()
mode=sys.argv[1] if len(sys.argv)>1 else ''
if mode=='api':
 if not os.environ.get('DB_PASSWORD'):raise SystemExit('.env.local DB_PASSWORD 설정 필요')
 if not os.environ.get('JAVA_HOME') and sys.platform=='darwin':
  os.environ['JAVA_HOME']=subprocess.check_output(['/usr/libexec/java_home','-v','25'],text=True).strip()
 os.chdir(ROOT/'backend');os.execv('./mvnw',['./mvnw','spring-boot:run','-Dspring-boot.run.profiles=local'])
elif mode=='worker':
 os.chdir(ROOT);os.environ['PYTHONPATH']=str(ROOT/'simulation');python=ROOT/'simulation/.venv/bin/python';os.execv(str(python),[str(python),'-m','waterleague_sim.worker',*sys.argv[2:]])
elif mode=='frontend':
 os.chdir(ROOT/'frontend');os.execvp('pnpm',['pnpm','dev'])
else:raise SystemExit('사용법: python3 scripts/run_local.py api|worker|frontend')
