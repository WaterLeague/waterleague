import unittest,json,tempfile,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from waterleague_sim.engine.swmm import run,experiment,library_path,score,SimulationQualityError,ROOT

class SwmmTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.model=json.loads((ROOT/'data/models/seongsu-lab.json').read_text())
  start=datetime(2024,1,1,tzinfo=timezone.utc)
  # 합성 강우는 수치 회귀시험 전용이며 공개 관측자료로 제공하지 않는다.
  cls.model['rainfall']={'start':start.isoformat(),'end':(start+timedelta(hours=8)).isoformat(),'intervalSeconds':60,'depthsMm':[.5]*120+[0]*360,'evidence':'SYNTHETIC_TEST_ONLY'}
 @unittest.skipUnless(library_path().exists(),'EPA 엔진 빌드 필요')
 def test_empty_strategy_is_deterministic_and_cli_matches(self):
  with tempfile.TemporaryDirectory() as d:
   a=run(self.model,[],d,'a');b=run(self.model,[],d,'b')
   self.assertEqual(a,b);self.assertEqual(score(a,b),0);self.assertLess(abs(a['runoffContinuityPercent']),1)
   exe=library_path().parent/'runswmm'
   subprocess.run([str(exe),str(Path(d)/'a.inp'),str(Path(d)/'cli.rpt'),str(Path(d)/'cli.out')],check=True,capture_output=True)
   def body(p):return p.read_text().split('Runoff Quantity Continuity',1)[1].split('Continuity Error (%)',1)[0]
   self.assertEqual(body(Path(d)/'a.rpt'),body(Path(d)/'cli.rpt'))
 @unittest.skipUnless(library_path().exists(),'EPA 엔진 빌드 필요')
 def test_all_lid_types_and_smaller_timestep(self):
  with tempfile.TemporaryDirectory() as d:
   for t in ['RAIN_GARDEN','PERMEABLE_PAVEMENT','GREEN_ROOF']:
    c=next(c for c in self.model['cells'] if t in c['allowedTypes'])
    placement=[{'cellId':c['id'],'facilityType':t,'areaM2':c['maxAreaM2']}]
    a=run(self.model,placement,d,t);b=run(self.model,placement,d,t+'fine',step_seconds=5)
    self.assertGreater(a['runoffM3'],0);self.assertLess(abs(a['runoffM3']-b['runoffM3'])/a['runoffM3'],.01)
 @unittest.skipUnless(library_path().exists(),'EPA 엔진 빌드 필요')
 def test_zero_rain_cannot_score(self):
  m=self.model|{'rainfall':self.model['rainfall']|{'depthsMm':[0]*480}}
  with tempfile.TemporaryDirectory() as d:
   a=run(m,[],d,'zero')
   with self.assertRaises(SimulationQualityError):score(a,a)
