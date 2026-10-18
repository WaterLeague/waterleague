"""서울시 공개 도시생태 원본의 표면 면적비와 DEM 격자 연결."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys
import unicodedata
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from audit_spatial_sources import command
from prepare_ngii_surface import prepare, sha, write
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.seoul_biotope import normalize, soil_cover_parameters
from waterleague_sim.terrain.composition import assign_composition
from waterleague_sim.terrain.coverage import PolygonLayer, projection
from waterleague_sim.terrain.topology import derive_consensus

MANIFEST = ROOT / 'data/manifests/seoul-biotope-20261018.json'
STEMS = {2025: '현장조사/현장조사_2025_수정_배포용', 2020: '현장조사', 2010: '현장조사/현장조사'}
FIELDS = '고유번호,건폐율,불투포장율,투수포장율,녹지율,기타비율,불투토포비,포장범례,토지이용'


def extract_survey(source, directory, year):
    require(not directory.exists(), 'BIOTOPE_EXTRACT_EXISTS')
    directory.mkdir(parents=True)
    selected = {}
    with ZipFile(source) as archive:
        require(len(archive.infolist()) <= 4096 and sum(i.file_size for i in archive.infolist()) < 600_000_000,
                'BIOTOPE_ARCHIVE_LIMIT')
        for item in archive.infolist():
            name = item.filename
            if not item.flag_bits & 2048:
                try:
                    name = name.encode('cp437').decode('cp949')
                except UnicodeError:
                    pass
            name = unicodedata.normalize('NFC', name)
            suffix = Path(name).suffix.lower()
            if name != STEMS[year] + suffix or suffix not in ('.shp', '.shx', '.dbf', '.prj'):
                continue
            require(suffix not in selected and not item.flag_bits & 1 and item.file_size <= 100_000_000
                    and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG), 'BIOTOPE_ARCHIVE_MEMBER_INVALID')
            raw = archive.read(item)
            require(len(raw) == item.file_size, 'BIOTOPE_ARCHIVE_SIZE_MISMATCH')
            target = directory / ('survey' + suffix)
            with target.open('xb') as stream:
                stream.write(raw)
            selected[suffix] = {'sourceName': name, 'bytes': len(raw), 'sha256': sha(target)}
    require(set(selected) == {'.shp', '.shx', '.dbf', '.prj'}, 'BIOTOPE_SURVEY_FILES_REQUIRED')
    return selected


def run(directory, year):
    require(not directory.exists(), 'BIOTOPE_OUTPUT_EXISTS')
    source = json.loads(MANIFEST.read_bytes())
    info = next(row for row in source['files'] if row['year'] == year and row['file'].endswith('.zip'))
    archive = ROOT / info['file']
    require(sha(archive) == info['sha256'] and archive.stat().st_size == info['bytes'],
            'BIOTOPE_ARCHIVE_HASH_MISMATCH')
    directory.mkdir(parents=True)
    original = directory / archive.name
    shutil.copyfile(archive, original)
    members = extract_survey(original, directory / 'survey', year)
    metadata = directory / 'survey/survey.prj'
    wkt = metadata.read_text()
    fields = FIELDS + (',자치구' if year != 2010 else '') + (',지붕유형' if year != 2025 else '')
    target = directory / 'native.json'
    command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', '-select', fields,
            target, directory / 'survey/survey.shp')
    records, attributes = normalize(json.loads(target.read_bytes())['features'], year)
    model, _ = prepare(directory / 'terrain')
    terrain = model['terrainProvenance']
    convert, operation = projection(wkt, terrain['coordinateWkt'], terrain['originProjected'],
                                    [127.03, 37.52, 127.08, 37.57])
    provenance = {'sourceArchive': info, 'archiveMembers': members, 'projection': operation,
        'nativeSha256': sha(target), 'sourceManifestSha256': sha(MANIFEST),
        'interpretationReference': source['reference'], 'editionYear': year,
        'gdalVersion': command('gdalinfo', '--version').strip()}
    derived, topology = derive_consensus(records, wkt)
    write(directory / 'topology.json', topology)
    cases, results = {}, {}
    for name, selected in (('original', records), ('derived-consensus', derived)):
        layer = PolygonLayer(selected, convert, provenance | {'geometryPolicy': name,
            'derivationSha256': sha(directory / 'topology.json') if name != 'original' else None})
        report = assign_composition(model, layer)
        write(directory / (name + '.json'), report)
        candidates, unresolved = soil_cover_parameters(layer.records,
            allocation_evidence='공개 블록 면적비의 격자 내 균질 배정 시나리오; 실제 포장 위치 미확인')
        write(directory / (name + '-soil-cover-candidates.json'), {'candidateParameters': candidates,
                                                                   'unresolved': unresolved})
        cases[name] = {'totals': report['totals'], 'validGeometries': len(layer.records),
            'invalidGeometries': len(layer.invalid), 'soilCoverCandidates': len(candidates),
            'additionalPhysicsRequired': len(unresolved),
            'resultSha256': sha(directory / (name + '.json'))}
        results[name] = report
    repeated = assign_composition(model, PolygonLayer(derived, convert, provenance | {
        'geometryPolicy': 'derived-consensus', 'derivationSha256': sha(directory / 'topology.json')}))
    require(results['derived-consensus'] == repeated, 'BIOTOPE_ASSIGNMENT_REPLAY_MISMATCH')
    summary = {'schemaVersion': 1, 'classification': 'PUBLIC_BLOCK_COMPOSITION_NOT_SITE_VALIDATED',
        'rankingEligible': False, 'editionYear': year, 'sourceArchiveSha256': info['sha256'],
        'attributes': attributes, 'cases': cases,
        'topology': {key: topology[key] for key in ('policy', 'adoptedCount', 'unresolvedCount')},
        'exactReplay': True, 'operationAccuracyM': operation['statedAccuracyM'],
        'limitations': results['derived-consensus']['limitations'] + topology['limitations']}
    sources = [Path(__file__), MANIFEST, ROOT / 'scripts/audit_spatial_sources.py',
        ROOT / 'simulation/waterleague_sim/ingestion/seoul_biotope.py',
        *sorted((ROOT / 'simulation/waterleague_sim/terrain').glob('*.py'))]
    for path in sources:
        target = directory / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    reference = ROOT / source['reference']['file']
    require(sha(reference) == source['reference']['sha256'], 'BIOTOPE_REFERENCE_HASH_MISMATCH')
    shutil.copyfile(reference, directory / 'reference.pdf')
    summary['sourceCode'] = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    write(directory / 'summary.json', summary)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'attributes': attributes, 'cases': cases, 'topology': summary['topology'],
        'files': len(files), 'manifestSha256': sha(directory / 'artifact-manifest.json')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--year', type=int, choices=(2010, 2020, 2025), default=2025)
    args = parser.parse_args()
    run(args.output.resolve(), args.year)
