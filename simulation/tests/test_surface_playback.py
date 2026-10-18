"""지도 투영 전후 원 프레임 보존 및 원 좌표 출처 검사."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pyproj import CRS, Transformer
import numpy as np

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.surface_frames import encode
from waterleague_sim.presentation.surface_playback import export_playback
from waterleague_sim.presentation.surface_directions import direction_basis, flow_direction, METHOD
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.terrain.grid import digest


class SurfacePlaybackTests(unittest.TestCase):
    def test_direction_rotation_projection_and_degenerate_rejection(self):
        convert = lambda x, y: (-2*y+100., 3*x-200.)
        basis, provenance = direction_basis(convert, [[10., 20.]])
        self.assertEqual(basis, [[0., -2., 3., 0.]])
        self.assertEqual(flow_direction(basis[0], 1, 0, .1), [0., 1.])
        self.assertEqual(flow_direction(basis[0], 0, 1, .1), [-1., 0.])
        self.assertIsNone(flow_direction(basis[0], 1, 1, 1e-6))
        self.assertIsNone(flow_direction(basis[0], 0, 0, .1))
        self.assertEqual(provenance['method'], METHOD)
        origin = Transformer.from_crs(4326, 32652, always_xy=True).transform(127., 37.5)
        transform = Transformer.from_crs(32652, 5186, always_xy=True, allow_ballpark=False)
        matrices, _ = direction_basis(transform.transform, [origin])
        projected = np.array(transform.transform(*origin))
        step = np.array(transform.transform(origin[0]+.1, origin[1]))-projected
        expected = step/np.linalg.norm(step)
        np.testing.assert_allclose(flow_direction(matrices[0], 1, 0, 1), expected, atol=1e-6)
        self.assertGreater(abs(expected[1]), .01)
        for invalid in (lambda x,y: (x,x), lambda x,y: (np.nan*x,y), lambda x,y: (x**3,y)):
            with self.assertRaises(FloodModelError): direction_basis(invalid, [[0., 0.]])

    def test_projected_mesh_and_unchanged_native_frames(self):
        source = {'coordinateWkt': CRS('EPSG:5186').to_wkt(), 'originProjected': [198128., 551989.]}
        model = mesh(1, 1) | {'schemaVersion': 2,
            'coordinateSystem': 'SOURCE_PROJECTED_LOCAL:'+digest(source), 'terrainProvenance': source,
            'startUtc': '2022-08-08T09:00:00Z',
            'frameOutput': {'schemaVersion':1,'type':'NATIVE_CENTROID_FLOAT64','maxFrames':10,'maxBytes':100000}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve()
            with EngineProcess('surface',model,path/'native') as session:
                session.call('advance',1.)
                session.call('finish')
            raw = (path/'native/surface-result.json').read_bytes()
            expected=hashlib.sha256(raw).hexdigest()
            city={'coordinateSystem':'EPSG:5186','originProjected':[198128.,551989.]}
            ref=export_playback(path/'native',expected,path/'display',city)
            catalog=json.loads((path/'display/catalog.json').read_bytes())
            self.assertEqual(catalog['schemaVersion'], 2)
            self.assertEqual(catalog['flowDirectionMethod'], METHOD)
            directions=json.loads((path/'display/mesh.json').read_bytes())['directionBasis']
            np.testing.assert_allclose(directions, [[1,0,0,1]]*len(model['triangles']), atol=1e-8)
            self.assertEqual(hashlib.sha256((path/'display/catalog.json').read_bytes()).hexdigest(),ref['catalogSha256'])
            self.assertEqual(json.loads((path/'display/mesh.json').read_bytes())['vertices'],model['verticesM'])
            for f in catalog['frames']:
                self.assertEqual((path/'display'/f['file']).read_bytes(),(path/'native/native-frames'/f['file']).read_bytes())
            self.assertEqual((path/'native/surface-result.json').read_bytes(),raw)
            self.assertFalse(catalog['rankingEligible'])
            with self.assertRaises(FloodModelError):
                export_playback(path/'native','0'*64,path/'bad',city)
            with self.assertRaises(FloodModelError):
                export_playback(path/'native',expected,path/'bad',city|{'coordinateSystem':'UNKNOWN'})
