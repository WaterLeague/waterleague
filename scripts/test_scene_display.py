"""공개 설치 후보와 도로 표시 보완 자료의 연결·공간 제약 검사."""
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from shapely.geometry import Polygon, LineString
from shapely import union_all
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'frontend/public/data'
def read(path):return json.loads(path.read_bytes())
def sha(raw):return hashlib.sha256(raw).hexdigest()
class DisplayTest(unittest.TestCase):
    def test_candidates_complete_and_reserved_excluded(self):
        manifest=read(ROOT/'data/manifests/site-display-v1.json')
        self.assertEqual(manifest['generatorSha256'],sha((ROOT/'scripts/prepare_site_display_tiles.py').read_bytes()))
        catalog=read(PUBLIC/'site-display-v1/catalog.json');rows={}
        for entry in catalog['tiles']:
            raw=(PUBLIC/'site-display-v1'/entry['file']).read_bytes()
            self.assertEqual((len(raw),sha(raw)),(entry['bytes'],entry['sha256']))
            for row in json.loads(raw):rows[(row[1],row[0])]=row
        occupancy=read(ROOT/'backend/src/main/resources/infrastructure/seoul-infrastructure-occupancy-20261019-v5.json')
        excluded={(r['districtId'],r['cellId']) for r in occupancy['exclusions']}
        self.assertFalse(excluded.intersection(rows));expected={}
        for version in (9,10):
            source=ROOT/'backend/src/main/resources/shared-sites'
            for entry in read(source/f'catalog-v{version}.json')['entries']:
                for cell in json.loads(gzip.decompress((source/entry['file']).read_bytes()))['cells']:
                    key=(entry['districtId'],cell['id'])
                    if cell['kind']=='GROUND' and key not in excluded:
                        expected[key]=sum(1<<catalog['types'].index(t) for t in cell['allowedTypes'])
        self.assertEqual(len(rows),547476);self.assertEqual(set(rows),set(expected))
        self.assertTrue(all(row[2]==expected[key] for key,row in rows.items()))
        self.assertTrue(any(len(read(PUBLIC/'site-display-v1'/entry['file']))>200 for entry in catalog['tiles']))
        overview=catalog['overview'];raw=(PUBLIC/'site-display-v1'/overview['file']).read_bytes()
        self.assertEqual(sha(raw),overview['sha256']);self.assertLess(len(raw),8_000_000)
        self.assertFalse(overview['picking']);self.assertEqual(overview['cellSizeM'],20)
        for row in json.loads(raw):self.assertTrue(Polygon(list(zip(row[3][::2],row[3][1::2])),[list(zip(h[::2],h[1::2])) for h in row[4]]).is_valid)
    def test_street_tags_bridges_and_clipped_walks(self):
        manifest=read(ROOT/'data/manifests/street-details-v1.json')
        self.assertEqual(manifest['generatorSha256'],sha((ROOT/'scripts/prepare_street_details.py').read_bytes()))
        original={};meta={}
        for entry in read(PUBLIC/'seoul-streets-v1/catalog.json')['tiles']:
            for row in read(PUBLIC/'seoul-streets-v1'/entry['file'])['roads']:original[row['id']]=row
        for entry in read(PUBLIC/'street-details-v1/catalog.json')['entries']:
            raw=(PUBLIC/'street-details-v1'/entry['file']).read_bytes()
            self.assertEqual((len(raw),sha(raw)),(entry['bytes'],entry['sha256']))
            for row in json.loads(raw):meta[row['id']]=row
        self.assertEqual(set(meta),set(original));self.assertEqual(sum(r['footway']=='crossing' for r in meta.values()),7350)
        hangang=[r for r in meta.values() if r['bridgeName']=='한강대교' and original[r['id']]['motor']]
        self.assertEqual(len(hangang),2)
        for row in hangang:
            self.assertEqual(row['structure'],'arch');self.assertTrue(row['structureSource'].startswith('https://news.seoul.go.kr/'))
            self.assertEqual(len(set(row['elevationsM'])),1);self.assertEqual(row['widthM'],13.5)
        checked=0
        for row in meta.values():
            source=original[row['id']]
            if 'elevationsM' in row:self.assertEqual(len(source['coordinates']),len(row['elevationsM']))
            if row.get('walkPolygons') and checked<100:
                area=union_all([Polygon(p[0],p[1:]) for p in row['walkPolygons']])
                before=LineString(source['coordinates']).buffer(row['widthM']/2,cap_style='flat',join_style='mitre')
                self.assertLessEqual(area.area,before.area+.1);self.assertTrue(area.is_valid);checked+=1
        self.assertEqual(checked,100)
if __name__=='__main__':unittest.main()
