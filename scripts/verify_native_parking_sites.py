"""주차장 추가본의 기존 레코드 보존·원형 포함·중복 제외·계산 입력 대조."""
import argparse,json,sqlite3,sys,math
from pathlib import Path
from contextlib import closing
import shapely
from shapely.geometry import shape
import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
from prepare_topography_objects import object_key
from prepare_native_parking_sites import BASE,BASE_SHA
sys.path.insert(0,str(source.ROOT/'simulation'))
from waterleague_sim.spatial import reference_conditions
from waterleague_sim.spatial.play_catalog import NativePlayCatalog
from waterleague_sim import installation_model
from waterleague_sim.engine import continuous
from unittest.mock import patch

def verify(report, engine_output=None):
    directory=BASE/'play-v2-parking';summary=json.loads((directory/'summary.json').read_bytes());raw=(directory/'parking-extension.json').read_bytes();evidence=json.loads(raw)
    assert source.digest(raw)==summary['extensionSha256']
    assert spatial.file_sha256(BASE/'play-v1/play.sqlite')==BASE_SHA
    catalog=NativePlayCatalog(directory/'play.sqlite',summary['playSha256'])
    count=0
    with closing(catalog.connection()) as db, closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro&immutable=1',uri=True)) as native:
        db.execute('ATTACH DATABASE ? AS old',('file:'+str(BASE/'play-v1/play.sqlite')+'?mode=ro&immutable=1',))
        assert db.execute('SELECT COUNT(*) FROM old.sites').fetchone()[0]==1023100
        assert db.execute('SELECT COUNT(*) FROM old.sites o LEFT JOIN main.sites s ON s.id=o.id WHERE s.id IS NULL OR s.body<>o.body OR s.object_id<>o.object_id OR s.allowed_mask<>o.allowed_mask OR s.fid<>o.fid').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM main.sites').fetchone()[0]==1023100+evidence['counts']['added']
        for row in evidence['decisions']:
            if row['status']!='ADDED':continue
            original=shapely.from_wkb(native.execute('SELECT geometry_wkb FROM features WHERE fid=?',(row['sourceFid'],)).fetchone()[0]);assert object_key('N1A_C0430000',original)==row['sourceId']
            cell=catalog.require(row['candidateId']);g=shape(cell['geometry'])
            assert g.is_valid and g.difference(original).area<1e-7
            assert abs(g.area-cell['areaM2'])<1e-7
            assert cell['role']=='PARKING_AREA' and cell['allowedTypes']==['PERMEABLE_PAVEMENT']
            reference_conditions.validate(cell)
            a,b,c,d=g.bounds
            for other,body in db.execute('SELECT s.id,s.body FROM main.site_bounds r JOIN main.sites s ON s.fid=r.fid WHERE r.maxx>=? AND r.minx<=? AND r.maxy>=? AND r.miny<=? AND s.kind=\'GROUND\' AND s.id<>?',(a,c,b,d,cell['id'])):
                assert g.intersection(shape(json.loads(body)['geometry'])).area<1e-7,(cell['id'],other)
            assert not catalog.accepts_catalog(BASE_SHA,cell['id'])
            assert catalog.model(cell['id'],district=cell['districtId'])['geometrySource']['sitesSha256']==summary['extensionSha256']
            count+=1
        original_id=db.execute('SELECT id FROM old.sites ORDER BY fid LIMIT 1').fetchone()[0]
        assert catalog.accepts_catalog(BASE_SHA,original_id) and catalog.accepts_catalog(BASE_SHA)
        assert not catalog.accepts_catalog('a'*64,original_id)
    engine_cases=[]
    if engine_output is not None:
        engine_output.mkdir(exist_ok=False)
        rain_path=source.ROOT/'data/models/seongsu-421-20240718.json'
        assert spatial.file_sha256(rain_path)=='fff031781cebc7f1b1f8e6cd0ed284c2166f688d80a2c70a2e4c24ee2df438c3'
        rain=json.loads(rain_path.read_bytes())['rainfall']
        selected=[row['candidateId'] for row in evidence['decisions'] if row['status']=='ADDED'][:3]
        with patch.object(installation_model,'open_catalog',return_value=catalog):
            old=catalog.require(original_id)
            installation_model.resolve(dict(district_id=old['districtId'],cell_id=original_id,model_hash=BASE_SHA))
            for identifier in selected:
                cell=catalog.require(identifier)
                try:
                    installation_model.resolve(dict(district_id=cell['districtId'],cell_id=identifier,model_hash=BASE_SHA))
                    raise AssertionError('새 후보에 이전 버전 허용')
                except ValueError as error:
                    assert str(error)=='LIVE_INSTALLATION_MODEL_INVALID'
                model,_,_=installation_model.resolve(dict(district_id=cell['districtId'],cell_id=identifier,model_hash=catalog.sha256))
                model['rainfall']=rain
                placement=catalog.placement(identifier,'PERMEABLE_PAVEMENT',min(30,cell['maxAreaM2']),district=cell['districtId'])
                output=engine_output/identifier
                result=continuous.experiment(model,placement,output)
                assert math.isclose(result['strategy']['final']['lidInflowM3'],placement['areaM2']*math.fsum(rain['depthsMm'])/1000,abs_tol=1e-5,rel_tol=1e-6)
                engine_cases.append(dict(candidateId=identifier,districtId=cell['districtId'],directRainVolumeMatched=True,engine=result['strategy']['engine'],resultSha256=spatial.file_sha256(output/'result.json')))
    result=dict(schemaVersion=1,status='PASS',catalogSha256=catalog.sha256,baseCatalogSha256=BASE_SHA,unchangedBaseRecords=1023100,verifiedParkingCandidates=count,allSourceFootprintsMatched=True,allGroundOverlapsExcluded=True,referenceInputsVerified=True,previousInstallationsCompatible=True,engineCases=engine_cases)
    report.write_text(source.canonical(result)+'\n');print(source.canonical(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--engine-output',type=Path);args=p.parse_args();verify(args.report,args.engine_output)
