"""워커가 발급한 로컬 작업 디렉터리에서만 실행하는 자식 프로세스."""
from pathlib import Path
import sys,json,resource,hashlib
from .engine.swmm import experiment
from .engine import swmm

def main():
 resource.setrlimit(resource.RLIMIT_CPU,(75,75));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
 if sys.platform.startswith('linux'):resource.setrlimit(resource.RLIMIT_AS,(1536*1024*1024,1536*1024*1024))
 path=Path(sys.argv[1]);model=json.loads((path/'model-source.json').read_text());request=json.loads((path/'request.json').read_text())
 if not model['simulationAvailable'] or model['validationLevel']!='EXPLORATORY':raise ValueError('MODEL_NOT_ELIGIBLE')
 if hashlib.sha256(Path(swmm.__file__).read_bytes()).hexdigest()!=model['generatorSha256']:raise ValueError('GENERATOR_MISMATCH')
 experiment(model,request['placements'],path)
if __name__=='__main__':main()
