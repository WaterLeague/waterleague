"""공개 Copernicus 지표면을 서울 지형 표시 격자로 재투영. 수문 입력과 분리."""
import argparse
import os
import hashlib
import json
import math
import subprocess
import sqlite3
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon
from shapely.strtree import STRtree
from local_config import ROOT

SOURCE = ROOT/'data/private/seoul-terrain-copernicus-20261018'
OUTPUT = ROOT/'frontend/public/data/seoul-terrain-native-v1'
OBJECTS = ROOT/'data/private/vworld-seoul-topography-20260307/objects-v1/objects.sqlite'
OBJECTS_SHA256 = '2c514899f82d858b4386d489b4fd9fa691552b59704f88f93e5475cc33b8f7d0'
RESOLUTION = 90


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',',':'), allow_nan=False)+'\n').encode()


def polygon(polygons):
    return MultiPolygon([Polygon(p[0], p[1:]) for p in polygons])


def build(output):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute(): raise ValueError('기존 원형 지형 출력 덮어쓰기 금지')
    sources = json.loads((SOURCE/'download-manifest.json').read_text())
    for item in sources:
        if sha((ROOT/item['file']).read_bytes()) != item['sha256']:
            raise ValueError('지표면 원본 해시 오류')
    city_raw = (ROOT/'frontend/public/data/seoul-native-v1/city.json').read_bytes()
    city = json.loads(city_raw)
    origin = city['originProjected']
    b = city['bounds']
    bounds = [math.floor((b[0]+origin[0])/90)*90-90, math.floor((b[1]+origin[1])/90)*90-90,
              math.ceil((b[2]+origin[0])/90)*90+90, math.ceil((b[3]+origin[1])/90)*90+90]
    inputs = [str(ROOT/i['file']) for i in sources if i['key'].endswith('_DEM.tif')]
    output.mkdir(parents=True)
    mosaic, projected = output/'seoul.vrt', output/'seoul-5186-90m.tif'
    subprocess.run(['gdalbuildvrt','-q',str(mosaic),*inputs],check=True)
    subprocess.run(['gdalwarp','-q','-overwrite','-t_srs','EPSG:5186','-te',*map(str,bounds),
        '-tr','90','90','-r','average','-dstnodata','-9999',str(mosaic),str(projected)],check=True)
    info = json.loads(subprocess.check_output(['gdalinfo','-json',str(projected)]))
    width, height = info['size'];gt = info['geoTransform']
    rows = subprocess.check_output(['gdal_translate','-q','-of','XYZ',str(projected),'/vsistdout/'],text=True).splitlines()
    heights = np.array([float(row.split()[2]) for row in rows],dtype='<f4')
    if len(heights) != width*height or not np.isfinite(heights).all() or heights.min() < -100 or heights.max() > 1500:
        raise ValueError('서울 지표면 높이 유효성 오류')
    east = gt[0]+(np.tile(np.arange(width),height)+.5)*gt[1]-origin[0]
    north = gt[3]+(np.repeat(np.arange(height),width)+.5)*gt[5]-origin[1]
    points = shapely.points(east, north)
    districts = np.zeros(width*height,dtype=np.uint8)
    for index, district in enumerate(city['districts'], 1):
        inside = shapely.covers(polygon(district['polygons']),points)
        districts[inside] = index
    cover = np.zeros(width*height,dtype=np.uint8)
    with OBJECTS.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != OBJECTS_SHA256:
            raise ValueError('원형 수면 카탈로그 해시 불일치')
    with sqlite3.connect(OBJECTS.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        polygons = [shapely.from_wkb(row[0]) for row in connection.execute(
            "SELECT geometry_wkb FROM objects WHERE role IN ('RIVER_WATER_AREA','LAKE_RESERVOIR_AREA') ORDER BY object_id")]
    tree = STRtree(polygons)
    pairs = tree.query(points, predicate='covered_by')
    cover[pairs[0]] = 2
    files = {}
    for name, data in (('height-f32le.bin',heights.tobytes()),('district-u8.bin',districts.tobytes()),('cover-u8.bin',cover.tobytes())):
        (output/name).write_bytes(data)
        files[name] = {'sha256':sha(data),'bytes':len(data)}
    notice = ('produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH '
        '2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.\n'
        'The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.\n'
        'District mask: 서울특별시·서울신용보증재단 OA-22161, 공공누리 제1유형.\n'
        'Water mask: 국토지리정보원 수치지형도v2.0(1:1000), 2026-03-07 갱신, 공공누리 제1유형.\n')
    (output/'attribution.txt').write_text(notice)
    license_file = next(SOURCE.rglob('eula_F.pdf'))
    (output/'copernicus-license.pdf').write_bytes(license_file.read_bytes())
    metadata = {'schemaVersion':1,'id':'seoul-copernicus-dsm-native-90m-v1','width':width,'height':height,
        'origin':[gt[0]+45-origin[0],gt[3]-45-origin[1]],'spacing':[90,-90],
        'districtIds':[d['id'] for d in city['districts']], 'files':files,
        'coordinateSystem':'EPSG:5186_LOCAL_TRANSLATION','originProjected':origin,
        'sourceResolutionM':30,'displayResolutionM':90,'verticalDatum':'EGM2008',
        'minM':float(heights.min()),'maxM':float(heights.max()),'citySha256':sha(city_raw),
        'waterObjectsSha256':OBJECTS_SHA256,'boundarySha256':'ff49da7030e1abcea4190aa3e3375714889fc537c2759cb4d220c04e764cf4c4',
        'coverPolicy':'FULL_NATIVE_WATER_ONLY_NO_INFERRED_GREEN',
        'gdalVersion':subprocess.check_output(['gdalinfo','--version'],text=True).strip(),
        'sourceUrl':'https://registry.opendata.aws/copernicus-dem/',
        'sourceRelease':'2021','modelInput':False,'attribution':notice,
        'limitations':['건물·수목을 포함하는 지표면 DSM; 지면 DTM·개별 지붕 경사 아님',
            '30m 원본을 90m 평균 격자로 재투영한 표시 자료; 미세 도로 턱과 시설 경사 미복원',
            '건물 밑면은 격자 보간의 표시 높이이며 현장 지반고 실측 아님','침수 수심·수문 입력에 사용하지 않음']}
    raw = encode(metadata);(output/'terrain.json').write_bytes(raw)
    manifest = metadata | {'files':files,'sourceFiles':sources,'metadataSha256':sha(raw),
        'generatorSha256':sha(Path(__file__).read_bytes())}
    (output/'manifest.json').write_bytes(encode(manifest))
    mosaic.unlink(); projected.unlink()
    print(json.dumps({'sha256':sha(raw),'width':width,'height':height,'bytes':sum(f['bytes'] for f in files.values()),'minM':metadata['minM'],'maxM':metadata['maxM']}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.output.absolute())
