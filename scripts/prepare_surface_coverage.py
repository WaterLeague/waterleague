"""보관 공개 토양·피복의 DEM 격자별 교차 면적과 미해결 입력 산출."""
import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from audit_spatial_sources import command, extract_checked
from prepare_ngii_surface import prepare, sha, write
from prepare_site_physics import SOILS
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.terrain.coverage import PolygonLayer, assign, infiltration_from_assignment, projection
from waterleague_sim.terrain.grid import digest

DIRECTORY = ROOT / 'data/private/seongsu-official-20261017'
LANDCOVER_SHA = '88456ce3a6ea11bd003ec9d9b0b7ebd67dd09d636a4dff572a083ebed18edf1f'
BOUNDS = [127.03, 37.52, 127.08, 37.57]


def soil_layer(directory, model):
    source = ROOT / 'data/manifests/seoul-soil-20261018.json'
    manifest = json.loads(source.read_bytes())
    require(manifest['crs'] == 'EPSG:4326' and manifest['total'] == 8266, 'SOIL_MANIFEST_CHANGED')
    files = {str(source.relative_to(ROOT)): sha(source)}
    records = []
    for page in manifest['pages']:
        path = (ROOT / page['file']).resolve()
        require(path.is_relative_to(ROOT / 'data/private/seoul-soil-20261018')
                and sha(path) == page['sha256'] and path.stat().st_size == page['bytes'],
                'SOIL_SOURCE_HASH_MISMATCH')
        features = json.loads(path.read_bytes())['response']['result']['featureCollection']['features']
        require(len(features) == page['count'], 'SOIL_FEATURE_COUNT_MISMATCH')
        records.extend(features)
        files[page['file']] = page['sha256']
    require(len(records) == manifest['total'], 'SOIL_FEATURE_COUNT_MISMATCH')
    for row in records:
        require(isinstance(row['properties'].get('label'), str) and row['properties']['label'],
                'SOIL_CLASS_MISSING')
    for name, expected in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        require(sha(target) == expected, 'SOIL_ARCHIVE_HASH_MISMATCH')
    terrain = model['terrainProvenance']
    convert, operation = projection(manifest['crs'], terrain['coordinateWkt'],
                                    terrain['originProjected'], BOUNDS)
    return PolygonLayer(records, convert, {'sourceFiles': files, 'projection': operation,
        'sourceUrl': manifest['sourceUrl'], 'acquiredAt': manifest['acquiredAt'],
        'observationDate': None, 'soilDepth': 'DEEP_SOIL_NOT_SURFACE_COMPACTION'})


def cover_layer(directory, model):
    archive = DIRECTORY / 'landcover-2024.zip'
    directory.mkdir(parents=True)
    require(sha(archive) == LANDCOVER_SHA, 'LANDCOVER_SOURCE_HASH_MISMATCH')
    shutil.copyfile(archive, directory / archive.name)
    extracted = directory / 'original'
    source = extract_checked(directory / archive.name, extracted, LANDCOVER_SHA)
    shp, prj = [extracted / ('37705083.' + ext) for ext in ('shp', 'prj')]
    target = directory / 'native.geojson'
    command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', target, shp)
    features = json.loads(target.read_bytes())['features']
    require(len(features) == 12330, 'LANDCOVER_COUNT_CHANGED')
    records = []
    for index, row in enumerate(features):
        props = row['properties']
        code, name, captured = [props.get(key) for key in ('L3_CODE', 'L3_NAME', 'IMG_DATE')]
        require(isinstance(code, str) and re.fullmatch('[0-9]{3}', code)
                and isinstance(name, str) and name.strip() and '\ufffd' not in name,
                'LANDCOVER_CLASS_INVALID')
        if captured:
            require(isinstance(captured, str) and date.fromisoformat(captured).isoformat() == captured,
                    'LANDCOVER_DATE_INVALID')
        records.append({'id': f'37705083:{index}', 'geometry': row['geometry'],
            'properties': {'classCode': code, 'className': name, 'imageDate': captured,
                           'originalPropertiesSha256': digest(props)}})
    terrain = model['terrainProvenance']
    convert, operation = projection(prj.read_text(), terrain['coordinateWkt'],
                                    terrain['originProjected'], BOUNDS)
    return PolygonLayer(records, convert, {'sourceArchiveSha256': LANDCOVER_SHA,
        'archiveMembers': source['members'], 'nativeConversionSha256': sha(target),
        'projection': operation, 'gdalVersion': command('gdalinfo', '--version').strip(),
        'editionYear': 2024, 'sourceUrl': 'https://egis.me.go.kr/',
        'limitation': '분류 경계와 영상 날짜이며 실측 불투수율·포장 재료·공극률 아님'})


def run(directory):
    require(not directory.exists(), 'COVERAGE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    model, terrain = prepare(directory / 'terrain')
    soil = soil_layer(directory / 'soil', model)
    cover = cover_layer(directory / 'landcover', model)
    report = assign(model, soil, cover)
    write(directory / 'coverage.json', report)
    replay = assign(model, soil, cover)
    require(report == replay, 'COVERAGE_REPLAY_MISMATCH')
    classifications = defaultdict(float)
    cover_by_id = {r['id']: r['properties'] for r in cover.records}
    soil_by_id = {r['id']: r['properties'] for r in soil.records}
    combinations = defaultdict(float)
    for cell in report['triangles']:
        for part in cell['landcover']['exclusiveParts']:
            props = cover_by_id[part['id']]
            classifications[(props['classCode'], props['className'])] += part['areaM2']
        for part in cell['jointParts']:
            label = soil_by_id[part['soilId']]['label']
            code = cover_by_id[part['landcoverId']]['classCode']
            combinations[(label, code)] += part['areaM2']
    try:
        infiltration_from_assignment(model, report, {}, {},
            initialization={'evidence': '미확보 입력 거부 검사', 'initialMoistureDeficit': .25, 'recoveryFactor': 1.})
    except FloodModelError as error:
        rejected = str(error)
    else:
        require(False, 'COVERAGE_UNRESOLVED_ACCEPTED')
    summary = {'schemaVersion': 1, 'classification': report['classification'], 'rankingEligible': False,
        'totals': report['totals'], 'sourceValidity': {
            'soil': {key: soil.provenance[key] for key in ('validFeatures', 'invalidFeatures')},
            'landcover': {key: cover.provenance[key] for key in ('validFeatures', 'invalidFeatures')}},
        'landcoverExclusiveClasses': [{'code': code, 'name': name, 'areaM2': area}
            for (code, name), area in sorted(classifications.items())],
        'jointClasses': [{'soil': label, 'landcoverCode': code, 'areaM2': area,
                         'literatureSoilCrosswalkAvailable': label in SOILS}
            for (label, code), area in sorted(combinations.items())],
        'sourceArchiveSha256': LANDCOVER_SHA, 'terrainArchiveSha256': terrain['sourceArchiveSha256'],
        'soilManifestSha256': sha(ROOT / 'data/manifests/seoul-soil-20261018.json'),
        'coverageSha256': sha(directory / 'coverage.json'), 'exactReplay': report == replay,
        'incompletePhysicsRejection': rejected, 'physicalParameters': report['physicalParameters'],
        'operationAccuracyM': {'soil': soil.provenance['projection']['statedAccuracyM'],
                              'landcover': cover.provenance['projection']['statedAccuracyM']},
        'limitations': report['limitations']}
    sources = [Path(__file__), ROOT / 'scripts/prepare_site_physics.py',
               ROOT / 'simulation/waterleague_sim/terrain/coverage.py',
               ROOT / 'simulation/waterleague_sim/engine/surface_infiltration.py']
    for path in sources:
        target = directory / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    summary['sourceCode'] = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    write(directory / 'summary.json', summary)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'totals': summary['totals'], 'sourceValidity': summary['sourceValidity'],
        'exactReplay': summary['exactReplay'], 'rejected': rejected,
        'artifactManifestSha256': sha(directory / 'artifact-manifest.json'), 'files': len(files)},
        ensure_ascii=False), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
