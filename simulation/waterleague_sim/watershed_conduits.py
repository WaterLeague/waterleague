"""공개 원 관로의 연결을 보존하는 단면·마찰 개량 입력."""
import json
import math
from pathlib import Path
from .engine.swmm import ROOT
from .engine.flood_errors import require
from .ingestion.published_network import records, digest

CATALOG=ROOT/'backend/src/main/resources/watersheds/seocho-conduits-v1.json'
CATALOG_HASH='a5dac5d1552b1620bfbe65c2f54a62626de16dd70a3807b1a2d03736ddcfdd6b'


def quantity(v, minimum, maximum, digits):
    require(type(v) in (int,float) and math.isfinite(v) and minimum<=v<=maximum
            and abs(v*10**digits-round(v*10**digits))<1e-6,'WATERSHED_CONDUIT_NUMBER_INVALID')
    return v


def compile(raw, design, source_raw, used_ids):
    catalog_raw=CATALOG.read_bytes()
    require(digest(catalog_raw)==CATALOG_HASH and isinstance(design,dict)
        and set(design)=={'schemaVersion','catalogHash','sourceNetworkSha256','placements'}
        and design['schemaVersion']==1 and design['catalogHash']==CATALOG_HASH,'WATERSHED_CONDUIT_CATALOG_INVALID')
    catalog=json.loads(catalog_raw)
    require(digest(source_raw)==catalog['baseNetworkSha256']==design['sourceNetworkSha256'],'WATERSHED_CONDUIT_SOURCE_CHANGED')
    text,sections=records(raw)
    links={r['tokens'][0]:r for r in sections['CONDUITS']}
    cross={r['tokens'][0]:r for r in sections['XSECTIONS']}
    sources={c['id']:c for c in catalog['conduits']}
    for c in sources.values():
        require(c['id'] in links and c['id'] in cross
            and links[c['id']]['tokens']==c['sourceConduitTokens']
            and cross[c['id']]['tokens']==c['sourceCrossSectionTokens'],'WATERSHED_CONDUIT_ORIGINAL_CHANGED')
    require(isinstance(design['placements'],list) and 0<len(design['placements'])<=20,'WATERSHED_CONDUIT_PLACEMENTS_INVALID')
    names={v.upper() for v in used_ids}; seen=set(); changes=[]
    lines=text.splitlines(keepends=True)
    def replace(row,tokens):
        line=lines[row['line']-1];ending='\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        comment=(' ;'+line.split(';',1)[1].rstrip('\r\n')) if ';' in line else ''
        lines[row['line']-1]=' '.join(tokens)+comment+ending
    for p in design['placements']:
        require(isinstance(p,dict) and set(p)=={'id','conduitId','shape','fullDepthM','widthM','barrels','roughness','basis','evidence','original'},'WATERSHED_CONDUIT_DESIGN_INVALID')
        from .engine.connected_storage import identifier
        identifier(p['id'])
        require(p['id'].upper() not in names and p['conduitId'] in sources and p['conduitId'] not in seen,'WATERSHED_CONDUIT_DUPLICATE_OR_UNKNOWN')
        names.add(p['id'].upper());seen.add(p['conduitId']); c=sources[p['conduitId']]
        require(p['basis']=='EXPLICIT_DESIGN_NOT_SITE_MEASURED' and isinstance(p['evidence'],str) and 1<=len(p['evidence'])<=500
            and p['original']==c['original'],'WATERSHED_CONDUIT_EVIDENCE_INVALID')
        require(p['shape'] in ('CIRCULAR','RECT_CLOSED') and type(p['barrels']) is int and 1<=p['barrels']<=20,'WATERSHED_CONDUIT_SHAPE_INVALID')
        quantity(p['fullDepthM'],.01,min(100,c['maxFullDepthM']),3);quantity(p['roughness'],.001,1,4)
        if p['shape']=='CIRCULAR': require(p['widthM'] is None,'WATERSHED_CONDUIT_CIRCULAR_WIDTH_INVALID')
        else: quantity(p['widthM'],.01,100,3)
        t=list(links[c['id']]['tokens']); x=list(cross[c['id']]['tokens'])
        if p['roughness']!=c['original']['roughness']:
            t[4]=format(p['roughness'],'.15g');replace(links[c['id']],t)
        if any(p[k]!=c['original'][k] for k in ('shape','fullDepthM','widthM','barrels')):
            x[1:7]=[p['shape'],format(p['fullDepthM'],'.15g'),format(p['widthM'] or 0,'.15g'),'0','0',str(p['barrels'])]
            replace(cross[c['id']],x)
        changes.append({'id':p['id'],'conduitId':c['id'],'fromNode':c['fromNode'],'toNode':c['toNode'],
            'lengthM':c['lengthM'],'original':c['original'], 'designed':{k:p[k] for k in c['original']},
            'changed':t!=links[c['id']]['tokens'] or x!=cross[c['id']]['tokens']})
    derived=''.join(lines).encode()
    return derived,{'schemaVersion':1,'method':'EXISTING_PUBLIC_CONDUIT_RETROFIT_V1',
        'catalogHash':CATALOG_HASH,'sourceNetworkSha256':digest(source_raw),'inputNetworkSha256':digest(raw),
        'derivedNetworkSha256':digest(derived),'compilerSha256':digest(Path(__file__).read_bytes()),
        'changes':changes,'limitations':catalog['limitations']}
