"""지도 투영 전후 원 프레임 보존 및 원 좌표 출처 검사."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from pyproj import CRS

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.surface_frames import encode
from waterleague_sim.presentation.surface_playback import export_playback
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.terrain.grid import digest


class SurfacePlaybackTests(unittest.TestCase):
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
