"""공개 관로 개량의 원 입력 보존·변조·중복 검증."""
import json
import unittest
from copy import deepcopy
from waterleague_sim.run_watershed_job import CATALOG,CATALOG_HASH,inputs
from waterleague_sim.ingestion.published_network import digest,records
from waterleague_sim.watershed_conduits import CATALOG as PIPES,CATALOG_HASH as PIPE_HASH,compile
from waterleague_sim.engine.flood_errors import FloodModelError


def request(d):
    raw=json.dumps(d,sort_keys=True)
    return {'modelHash':CATALOG_HASH,'placements':raw,'inputHash':digest((CATALOG_HASH+'\n'+raw).encode())}


def design():
    c=json.loads(CATALOG.read_text());pipes=json.loads(PIPES.read_text());original=pipes['conduits'][0]['original']
    return {'schemaVersion':1,'basis':c['designBasis'],'placements':[], 'conduits':{
        'schemaVersion':1,'catalogHash':PIPE_HASH,'sourceNetworkSha256':pipes['baseNetworkSha256'],
        'placements':[{'id':'Pipe1','conduitId':'C1',**original,'basis':'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
            'evidence':'회원 지정 관로 개량 시험; 현장 관측 제원 아님','original':original}]}}


class ConduitTests(unittest.TestCase):
    def test_identical_design_preserves_bytes_and_edits_only_selected_properties(self):
        d=design();_,_,base,strategy,_,meta,_=inputs(request(d))
        self.assertEqual(base,strategy)
        self.assertFalse(meta['conduitRetrofits']['changes'][0]['changed'])
        d['conduits']['placements'][0].update(shape='CIRCULAR',widthM=None,fullDepthM=2.4,roughness=.013,barrels=2)
        _,_,before,after,_,_,_=inputs(request(d))
        bs=records(before)[1];as_=records(after)[1]
        for section in bs:
            if section not in ('CONDUITS','XSECTIONS'): self.assertEqual(bs[section],as_[section])
        self.assertEqual(bs['CONDUITS'][1:],as_['CONDUITS'][1:])
        self.assertEqual(bs['XSECTIONS'][1:],as_['XSECTIONS'][1:])
        self.assertEqual(as_['CONDUITS'][0]['tokens'][1:4],bs['CONDUITS'][0]['tokens'][1:4])
        self.assertEqual(as_['CONDUITS'][0]['tokens'][5:],bs['CONDUITS'][0]['tokens'][5:])
        self.assertEqual(as_['XSECTIONS'][0]['tokens'][1:7],['CIRCULAR','2.4','0','0','0','2'])

    def test_rejects_foreign_sources_duplicate_links_and_invalid_geometry(self):
        for change in ({'conduitId':'NEW_PIPE'},{'widthM':None},{'roughness':0},{'fullDepthM':3.201},{'barrels':1.5},{'fullDepthM':float('nan')}):
            d=design();d['conduits']['placements'][0].update(change)
            with self.assertRaises(FloodModelError): inputs(request(d))
        d=design();d['conduits']['placements'].append(deepcopy(d['conduits']['placements'][0])|{'id':'Pipe2'})
        with self.assertRaises(FloodModelError): inputs(request(d))
        d=design();d['conduits']['sourceNetworkSha256']='0'*64
        with self.assertRaises(FloodModelError): inputs(request(d))
        d=design();d['conduits']['placements'][0]['original']['roughness']=.1
        with self.assertRaises(FloodModelError): inputs(request(d))
        d=design();base=inputs(request(d))[2]
        row=records(base)[1]['CONDUITS'][0]['text']
        modified=base.replace(row.encode(),row.replace('J1','J9',1).encode(),1)
        self.assertNotEqual(base,modified)
        with self.assertRaises(FloodModelError): compile(modified,d['conduits'],base,[])
        with self.assertRaises(FloodModelError): compile(base,d['conduits'],base,['Pipe1'])
