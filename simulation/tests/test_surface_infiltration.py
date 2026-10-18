"""원본 EPA 대조·해석 수지·관측 강우·결합 침투 검사. 현장 정확도 검증 아님."""
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor
import ctypes as C
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network import NetworkSession
from waterleague_sim.engine.surface_infiltration import SoilBank, validate
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh, tank_input
from test_observed_surface_rainfall import observed_coupled, specification


def soils(model, *, conductivity=36., deficit=0., fraction=1.):
    return {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1.,
        'evidence': 'NUMERICAL_TEST_ONLY', 'imperviousTriangles': [], 'regions': [{
            'triangles': [i for i, owner in enumerate(model['rainfallOwner']) if owner == 'SURFACE'],
            'perviousFraction': fraction, 'suctionMm': 100., 'conductivityMmH': conductivity,
            'initialMoistureDeficit': deficit, 'evidence': 'NUMERICAL_TEST_ONLY'}]}


class GrnAmpt(C.Structure):
    _fields_ = [(name, C.c_double) for name in ('S', 'Ks', 'IMDmax', 'IMD', 'F', 'Fu', 'Lu', 'T')]
    _fields_.append(('Sat', C.c_char))


def native_reference(parameters, modified, events):
    # 원본 관망 빌드의 OpenMP를 ANUGA 테스트 프로세스에 로드하지 않는다.
    with tempfile.TemporaryDirectory() as temporary:
        with NetworkSession(tank_input(), Path(temporary) / 'reference', evaluation_seconds=120) as native:
            lib = native.lib
            lib.grnampt_setParams.argtypes = [C.POINTER(GrnAmpt), C.POINTER(C.c_double)]
            lib.grnampt_initState.argtypes = [C.POINTER(GrnAmpt)]
            lib.grnampt_getInfil.argtypes = [C.POINTER(GrnAmpt), C.c_double, C.c_double, C.c_double, C.c_int]
            lib.grnampt_getInfil.restype = C.c_double
            states = [GrnAmpt() for _ in parameters]
            for state, params in zip(states, parameters):
                if lib.grnampt_setParams(C.byref(state), (C.c_double * 3)(*params)) != 1:
                    raise RuntimeError('EPA_REFERENCE_PARAMETERS_INVALID')
                lib.grnampt_initState(C.byref(state))
            results = []
            for dt, rain, ponded in events:
                values = [lib.grnampt_getInfil(C.byref(s), dt, rain / 3_600_000 / .3048,
                          ponded / .3048, 3 if modified else 2) * dt * .3048 for s in states]
                results.append((values, [[s.IMD, s.F, s.Fu, ord(s.Sat), s.T] for s in states]))
            return results


class SoilBankTests(unittest.TestCase):
    def test_native_wet_dry_recovery_matches_unmodified_epa_functions(self):
        import numpy as np
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
            for modified in (False, True):
                parameters = [[100., 3.302, .3], [60.96, 29.972, .1]]
                bank = SoilBank(parameters)
                events = [(60, 60., .01)] * 60 + [(3600, 0., 0.)] * 48 + [(60, 90., .02)] * 30
                reference = pool.submit(native_reference, parameters, modified, events).result(timeout=30)
                for (dt, rain, ponded), (values, state) in zip(events, reference):
                    actual = bank.advance(dt, [rain / 3_600_000] * 2, [ponded] * 2,
                                          modified=modified, recovery=1.)
                    np.testing.assert_array_equal(actual, values)
                    np.testing.assert_array_equal(bank.state(), state)

    def test_required_coverage_ownership_and_parameters(self):
        model = mesh(1, 1)
        spec = soils(model)
        cases = []
        bad = deepcopy(spec); bad['regions'][0]['triangles'].pop(); cases.append((bad, 'COVERAGE_INCOMPLETE'))
        bad = deepcopy(spec); bad['imperviousTriangles'] = [0]; cases.append((bad, 'REGION_INVALID'))
        bad = deepcopy(spec); bad['regions'][0]['conductivityMmH'] = 0; cases.append((bad, 'PARAMETERS_INVALID'))
        bad = deepcopy(spec); bad['regions'][0]['perviousFraction'] = 1.1; cases.append((bad, 'PARAMETERS_INVALID'))
        bad = deepcopy(spec); bad['regions'][0]['suctionMm'] = float('nan'); cases.append((bad, 'PARAMETERS_INVALID'))
        for value, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(FloodModelError, code):
                validate(value, model['rainfallOwner'])
        model['rainfallOwner'][0] = 'NETWORK'
        with self.assertRaisesRegex(FloodModelError, 'DOUBLE_COUNT'):
            validate(spec, model['rainfallOwner'])


class SurfaceInfiltrationTests(unittest.TestCase):
    def test_ponded_saturated_infiltration_area_and_replay(self):
        import numpy as np
        model = mesh(2, 2, water=lambda x, z: np.full(len(x), .02))
        model.update(schemaVersion=2, infiltration=soils(model, fraction=.5))
        finals = []
        with tempfile.TemporaryDirectory() as temporary:
            for name, segments in [('whole', [60]), ('segmented', [10] * 6), ('replay', [60])]:
                directory = Path(temporary) / name
                with EngineProcess('surface', model, directory) as engine:
                    for dt in segments:
                        final = engine.call('advance', dt)
                    result = engine.call('finish')
                self.assertAlmostEqual(final['infiltrationM3'], .03, places=10)
                self.assertAlmostEqual(final['storageM3'], 1.97, places=10)
                self.assertEqual(final['rainfallM3'], 0.)
                self.assertLess(abs(final['balanceResidualM3']), 1e-9)
                self.assertEqual(result['numericalStatus'], 'PASSED')
                state = json.loads((directory / 'surface-infiltration.json').read_text())
                self.assertEqual(len(state['nativeState']), len(model['triangles']))
                self.assertEqual(state['effectivePerviousAreaM2'], 50.)
                finals.append(final)
            self.assertEqual(finals[0], finals[2])
            np.testing.assert_allclose(finals[0]['depthM'], finals[1]['depthM'], atol=1e-12)

    def test_all_rain_infiltrates_without_negative_depth_or_false_missing_rain(self):
        model = mesh(2, 2)
        model.update(schemaVersion=2, infiltration=soils(model, conductivity=1000, deficit=.3))
        rain = specification(model, end='2022-08-08T09:02:00Z')
        with tempfile.TemporaryDirectory() as temporary:
            result = run_observed_surface(model, rain, Path(temporary) / 'run')
        self.assertAlmostEqual(result['observedRainfall']['appliedSurfaceRainfallM3'], .15, places=10)
        self.assertAlmostEqual(result['final']['infiltrationM3'], .15, places=10)
        self.assertAlmostEqual(result['final']['sourceNetInflowM3'], 0., places=10)
        self.assertAlmostEqual(result['final']['storageM3'], 0., places=10)
        self.assertGreaterEqual(min(result['final']['depthM']), 0.)
        self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_distinct_soils_and_explicit_impervious_cells(self):
        model = mesh(1, 1, water=lambda x, z: x * 0 + .02)
        spec = soils(model)
        spec['regions'][0]['triangles'] = [0]
        spec['imperviousTriangles'] = [1]
        model.update(schemaVersion=2, infiltration=spec)
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', model, Path(temporary) / 'run') as engine:
                final = engine.call('advance', 10)
                engine.call('finish')
            self.assertAlmostEqual(final['infiltrationM3'], .005, places=10)
            self.assertAlmostEqual(final['storageM3'], 1.995, places=10)

    def test_observed_coupled_rain_and_infiltration_have_separate_ledgers(self):
        model = observed_coupled()
        model['surface'].update(schemaVersion=2, infiltration=soils(model['surface'], conductivity=3.302, deficit=.3))
        with tempfile.TemporaryDirectory() as temporary:
            result = run_coupled(model, Path(temporary) / 'run')
        balance = result['balance']
        self.assertAlmostEqual(result['observedRainfall']['appliedSurfaceRainfallM3'], .006, places=10)
        self.assertGreater(balance['surfaceInfiltrationM3'], 0.)
        self.assertAlmostEqual(balance['surfaceRainfallM3'] - balance['surfaceInfiltrationM3']
            + balance['surfaceBoundaryNetInflowM3'], balance['surfaceExternalNetInflowM3'], places=9)
        self.assertLess(abs(balance['exchangeCancellationResidualM3']), 1e-8)
        self.assertEqual(result['numericalStatus'], 'PASSED')


if __name__ == '__main__':
    unittest.main()
