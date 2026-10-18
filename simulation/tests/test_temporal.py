"""설치 시각 경계·음의 효과·동일 입력 재생의 네이티브 수치 검증."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from test_continuous import model_for
from waterleague_sim.engine import continuous, swmm


@unittest.skipUnless(continuous.library_path().exists(), '상태 관측 엔진 빌드 필요')
class TemporalTests(unittest.TestCase):
    def test_second_boundary_conservation_replay_and_no_prorating(self):
        model, placement = model_for('GREEN_ROOF', [2]*30+[0]*30)
        cell = model['cells'][0]
        cell['physicalInputs'] = {'runoffWidthM': cell['areaM2']**.5,
                                 'flowLengthM': cell['areaM2']**.5, 'slopePercent': 1}
        start = datetime.fromisoformat(model['rainfall']['start'])
        at = (start+timedelta(seconds=1217)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            full = continuous.experiment(model, placement, root/'full')
            timed = continuous.experiment(model, placement, root/'timed', installed_at=at)
            again = continuous.experiment(model, placement, root/'again', installed_at=at)
            origin = continuous.experiment(model, placement, root/'origin', installed_at=start.isoformat())
            self.assertEqual(full['contribution'], origin['contribution'])
            self.assertEqual(timed, again)
            for name in ('baseline', 'strategy'):
                case = timed[name]
                self.assertEqual(case['initial']['at'], at)
                self.assertEqual(case['initial']['accountedDischargeM3'], 0)
                self.assertEqual(case['samples'][0]['elapsedSeconds'], 43)
                self.assertEqual(case['runoffMetrics']['stepCount'], 3600-1217)
                self.assertLess(abs(case['final']['balanceResidualM3']), .01*case['final']['initialStorageM3'] + 1e-7)
                self.assertEqual((root/'full'/f'{name}.inp').read_bytes(), (root/'timed'/f'{name}.inp').read_bytes())
                self.assertEqual((root/'full'/f'{name}.out').read_bytes(), (root/'timed'/f'{name}.out').read_bytes())
                self.assertEqual((root/'timed'/f'{name}.out').read_bytes(), (root/'again'/f'{name}.out').read_bytes())
            self.assertAlmostEqual(sum(p['incrementM3'] for p in timed['contribution']),
                                   timed['runoffComparison']['accountedReductionM3'])
            self.assertNotAlmostEqual(timed['contribution'][-1]['cumulativeM3'],
                                      full['contribution'][-1]['cumulativeM3']*(3600-1217)/3600)
            self.assertIn('temporal.py', json.loads((root/'timed/manifest.json').read_text()))
            tail = continuous.experiment(model, placement, root/'tail',
                                        installed_at=(start+timedelta(seconds=3599)).isoformat())
            self.assertEqual(tail['strategy']['runoffMetrics']['observedSeconds'], 1)
            self.assertEqual(len(tail['contribution']), 1)

    def test_invalid_activation_fails_before_execution(self):
        model, placement = model_for('GREEN_ROOF', [0]*2)
        start = datetime.fromisoformat(model['rainfall']['start'])
        with tempfile.TemporaryDirectory() as d:
            for at in (start-timedelta(seconds=1), start+timedelta(minutes=2),
                       start+timedelta(microseconds=1), start+timedelta(seconds=1)):
                with self.assertRaises(swmm.SimulationQualityError):
                    continuous.experiment(model, placement, Path(d), installed_at=at.isoformat())
            self.assertEqual(list(Path(d).rglob('*.inp')), [])
