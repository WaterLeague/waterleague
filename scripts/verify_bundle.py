"""재현 ZIP의 해시 검증과 설치된 동일 빌더·엔진으로 수치 재실행."""
import argparse,hashlib,json,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim.engine import swmm

parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path);parser.add_argument('--rerun',action='store_true');args=parser.parse_args()
with zipfile.ZipFile(args.bundle) as z:
 entries=z.infolist()
 if len(entries)>40 or sum(p.file_size for p in entries)>128*1024*1024:raise SystemExit('파일 크기 상한 초과')
 if len({p.filename for p in entries})!=len(entries) or any(Path(p.filename).name!=p.filename for p in entries):raise SystemExit('파일 이름 거부')
 manifest=json.loads(z.read('manifest.json'))
 for name,digest in manifest.items():
  if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise SystemExit('해시 불일치: '+name)
 model=json.loads(z.read('model-source.json'));placements=json.loads(z.read('placements.json'));result=json.loads(z.read('result.json'))
 print('실행 원본',len(manifest),'개 해시 일치; 통화',model['currency'],'근거',model['costEvidence'])
 if args.rerun:
  # 묶음의 Python 코드는 실행하지 않고 현재 설치된 검증 빌더만 사용한다.
  if hashlib.sha256(Path(swmm.__file__).read_bytes()).hexdigest()!=result['engine']['generatorSha256']:raise SystemExit('동일 빌더 버전 체크아웃 필요')
  if hashlib.sha256(swmm.library_path().read_bytes()).hexdigest()!=result['engine']['binarySha256']:raise SystemExit('동일 엔진 바이너리 필요')
  with tempfile.TemporaryDirectory() as tmp:
   replay=swmm.experiment(model,placements,tmp)
   for field in ['score','baseline','strategy','sensitivity']:
    if replay[field]!=result[field]:raise SystemExit('재실행 불일치: '+field)
  print('기준안·배치안·민감도·분 시계열 동일 재현')
