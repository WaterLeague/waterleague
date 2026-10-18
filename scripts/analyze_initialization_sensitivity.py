"""등록 재해·공개 후보의 선행 7/14/28일과 건습 시드를 같은 평가 창에서 비교."""
import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from local_config import ROOT, load
from prepare_antecedent_weather import archived_forcing
from prepare_disaster_evaporation import saved as network_saved

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine import initialization_sensitivity as study
from waterleague_sim.ingestion import live, antecedent
from waterleague_sim.ingestion.rainfall import RainfallQualityError
from waterleague_sim.historical_antecedent import load as load_prior
from waterleague_sim.historical_evaporation import load as load_pet
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.shared_model import resolve, candidates, site_catalog, with_observed_forcing


def saved(endpoint, parameters, key):
    if not key:
        raw = (json.dumps({'endpoint': endpoint, 'parameters': parameters}, ensure_ascii=False,
                          indent=2, allow_nan=False)+'\n').encode()
        stem = 'kma-disaster-pet-'+hashlib.sha256(raw).hexdigest()[:24]
        if not (ROOT/'data/raw'/(stem+'.txt')).is_file():
            raise ValueError('SPINUP_ARCHIVED_SOURCE_MISSING')
    return network_saved(endpoint, parameters, key)


def archived_weather(start, end, key):
    periods, cursor = [], start
    while cursor < end:
        midnight = cursor.astimezone(live.KST).replace(hour=0, minute=0, second=0, microsecond=0)
        limit = min(end, midnight + timedelta(days=1))
        periods.append((cursor, limit))
        cursor = limit

    def collect(period):
        result, _ = antecedent.weather(*period, key, saved)
        print('선행 기상 원문 확인', period[0].date().isoformat(), flush=True)
        return result

    # 날짜별 요청 파일은 서로 다르며 결과는 원래 시간 순서로 결합한다.
    with ThreadPoolExecutor(max_workers=3) as pool:
        parts = list(pool.map(collect, periods))
    return {'method': antecedent.METHOD,
            'ratesMmDay': [v for p in parts for v in p['ratesMmDay']],
            'sourceHashes': sorted({v for p in parts for v in p['sourceHashes']}),
            'sourceRequests': [v for p in parts for v in p['sourceRequests']],
            'segments': [v for p in parts for v in p['segments']],
            'assumptions': sorted({v for p in parts for v in p['assumptions']})}


def extend(short, days, key):
    if days == 7:
        return short
    end = datetime.fromisoformat(short['rainfall']['start'])
    start = end-timedelta(days=days-7)
    # 저장 원문을 우선하며 새 조회는 --fetch 실행에서만 허용한다.
    def fetch_aws(station, a, b, token):
        try:
            return saved(live.ENDPOINT, {'tm1': a.astimezone(live.KST).strftime('%Y%m%d%H%M'),
                                         'tm2': b.astimezone(live.KST).strftime('%Y%m%d%H%M'),
                                         'stn': station, 'disp': '0', 'help': '1'}, token)
        except ValueError as error:
            if str(error).startswith(('기상청 HTTP 504:', '기상청 원본 수집 실패:')):
                raise live.LiveSourceError('KMA_UNAVAILABLE') from None
            raise
    live.fetch_range = fetch_aws
    options = {'chunk_hours': 6, 'antecedent_quality': True,
               'heartbeat': lambda: print('선행 강우 원문 확인', flush=True)}
    try:
        forcing, sources = archived_forcing(short['rainfall']['stationId'], start, end, '', **options)
        print('보관 선행 강우 원문 재사용', flush=True)
    except RainfallQualityError as error:
        if not key or str(error) != 'AWS_REQUIRED_MINUTE_MISSING':
            raise
        forcing, sources = live.observed_forcing(short['rainfall']['stationId'], start, end, key, **options)
    rain = {k: forcing[k] for k in ('start', 'end', 'stationId', 'intervalSeconds', 'sourceHashes',
                                   'evidence', 'qualityWarnings', 'qualityPolicy', 'aggregatedRainIntervals')}
    rain.update(depthsMm=[v['depthMm'] for v in forcing['observations']],
                depthMethods=[v['method'] for v in forcing['observations']], sourceRequests=[s for _, s in sources])
    rain['reconstructedMinutes'] = sum(v.startswith('OBSERVED_ZERO_') for v in rain['depthMethods'])
    pet = archived_weather(start, end, key)
    rain['end'] = short['rainfall']['end']
    for k in ('depthsMm', 'depthMethods', 'qualityWarnings', 'aggregatedRainIntervals', 'sourceRequests'):
        rain[k] += short['rainfall'][k]
    rain['sourceHashes'] = sorted(set(rain['sourceHashes']+short['rainfall']['sourceHashes']))
    rain['reconstructedMinutes'] += short['rainfall']['reconstructedMinutes']
    for k in ('ratesMmDay', 'segments', 'sourceRequests'):
        pet[k] += short['evaporation'][k]
    pet['sourceHashes'] = sorted(set(pet['sourceHashes']+short['evaporation']['sourceHashes']))
    pet['assumptions'] = sorted(set(pet['assumptions']+short['evaporation']['assumptions']))
    return {'rainfall': rain, 'evaporation': pet}


def archive_sources(prior, root):
    entries = {}
    for kind in ('rainfall', 'evaporation'):
        for source in prior[kind]['sourceRequests']:
            sha, name = source['sha256'], source['rawFile']
            if (not re.fullmatch('[a-f0-9]{64}', sha)
                    or not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}.txt', name)):
                raise ValueError('SPINUP_SOURCE_INVALID')
            raw = (ROOT/name).read_bytes()
            if study.continuous.digest(raw) != sha:
                raise ValueError('SPINUP_SOURCE_INVALID')
            (root/('s'+sha+'.txt')).write_bytes(raw)
            entries[sha] = source
    return entries


def archive_registered_source(name, expected, root):
    if not re.fullmatch(r'kma-[A-Za-z0-9-]+\.json', name):
        raise ValueError('SPINUP_SOURCE_INVALID')
    manifest = (ROOT/'data/manifests'/name).read_bytes()
    meta = json.loads(manifest)
    raw = (ROOT/'data/raw'/(name.removesuffix('.json')+'.txt')).read_bytes()
    if meta['sha256'] != expected or study.continuous.digest(raw) != expected:
        raise ValueError('SPINUP_SOURCE_INVALID')
    (root/('s'+expected+'.txt')).write_bytes(raw)
    (root/('source-'+name)).write_bytes(manifest)


def reproduce(directory):
    manifest = json.loads((directory/'manifest.json').read_bytes())
    for name, sha in manifest.items():
        if not re.fullmatch('[A-Za-z0-9_.-]+', name) or study.continuous.digest((directory/name).read_bytes()) != sha:
            raise ValueError('SPINUP_ARCHIVE_INVALID')
    request = json.loads((directory/'input.json').read_bytes())
    expected = json.loads((directory/'sensitivity.json').read_bytes())
    with tempfile.TemporaryDirectory() as root:
        actual = study.analyze(**request, directory=Path(root))
    if actual != expected:
        raise ValueError('SPINUP_REPLAY_MISMATCH')
    print('동일 입력·엔진의 비교 결과 재현 일치', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', default='seoul-20220808')
    parser.add_argument('--district', default='2419953')
    parser.add_argument('--days', type=int, choices=(14, 28), default=14)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    if args.replay:
        reproduce(args.replay)
        return
    root = args.output or ROOT/'data/runs'/f'initialization-{args.event}-{args.district}-{args.days}d'
    if root.exists() and any(root.iterdir()):
        raise ValueError('SPINUP_OUTPUT_ALREADY_EXISTS')
    root.mkdir(parents=True, exist_ok=True)
    events = json.loads((ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())['events']
    event = next(v for v in events if v['id'] == args.event)
    sources = read_catalog(ROOT/'data/models')
    observed_hash = next(v['modelHash'] for v in event['models']
                         if json.loads(sources[v['modelHash']])['mapId'] == 'seoul-osm-v1-'+args.district)
    observed = json.loads(sources[observed_hash])
    (root/'rainfall-model.json').write_bytes(sources[observed_hash])
    rain = observed['rainfall']
    archive_registered_source(rain['sourceManifest'], rain['sourceHash'], root)
    station = rain['stationMetadata']
    archive_registered_source(station['sourceManifest'], station['sourceSha256'], root)
    archive_registered_source(station['endSourceManifest'], station['endSourceSha256'], root)
    short, pet = load_prior(observed_hash, root), load_pet(observed_hash, observed, root)
    if args.fetch:
        load()
    prior = extend(short, args.days, os.environ.get('KMA_API_KEY', '') if args.fetch else '')
    provenance = archive_sources(prior, root)
    (root/'extended-antecedent.json.gz').write_bytes(gzip.compress(study.encode(prior), mtime=0))
    periods = tuple(day for day in (7, 14, 28) if day <= args.days)
    reports = []
    available = candidates(args.district)
    for facility in ('RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF'):
        cell = min((c for c in available.values() if facility in c['allowedTypes'] and c['maxAreaM2'] >= 20),
                   key=lambda c: (c['areaM2'], c['id']))
        model, _, _ = resolve({'district_id': args.district, 'cell_id': cell['id'],
                                'model_hash': site_catalog()[args.district]['sha256']})
        model['rainfall'] = observed['rainfall']
        model = with_observed_forcing(model, pet)
        placement = {'cellId': cell['id'], 'facilityType': facility, 'areaM2': 20.0}
        report = study.analyze(model, placement, pet, prior, root/facility, days=periods)
        reports.append(report)
        print(facility, report['comparison']['status'], flush=True)
    raw_hashes = sorted(p.stem[1:] for p in root.glob('s*.txt') if re.fullmatch('s[a-f0-9]{64}', p.stem))
    summary = {'schemaVersion': 1, 'eventId': args.event, 'districtId': args.district, 'days': list(periods),
               'assetTemporalMode': 'CURRENT_GEOMETRY_HISTORICAL_RAIN_STRESS_TEST',
               'evaluationModelHash': observed_hash, 'siteCatalogHash': site_catalog()[args.district]['sha256'],
               'antecedentSourceCount': len(provenance), 'sourceCount': len(raw_hashes),
               'sourceHashes': raw_hashes, 'reports': reports}
    (root/'summary.json').write_bytes(study.encode(summary))
    (root/'analyze_initialization_sensitivity.py').write_bytes(Path(__file__).read_bytes())
    for module in ('ingestion/live.py', 'ingestion/antecedent.py', 'ingestion/kma.py',
                   'ingestion/daily_evaporation.py', 'engine/evapotranspiration.py'):
        (root/('extended-'+module.replace('/', '-'))).write_bytes((ROOT/'simulation/waterleague_sim'/module).read_bytes())
    for name in ('prepare_antecedent_weather.py', 'prepare_disaster_evaporation.py'):
        (root/('extended-'+name)).write_bytes((ROOT/'scripts'/name).read_bytes())
    (root/'manifest.json').write_bytes(study.encode({str(p.relative_to(root)): study.continuous.digest(p.read_bytes())
        for p in sorted(root.rglob('*')) if p.is_file() and p != root/'manifest.json'}))
    print('민감도 비교 묶음 생성 완료', flush=True)


if __name__ == '__main__':
    main()
