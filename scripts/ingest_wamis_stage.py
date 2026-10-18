"""공개 웹 시자료 원문과 정규화 결과를 날짜별 불변 묶음으로 보관."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.wamis_stage import normalize

GAUGE_STATIONS = {'1018662': '서울시(청담대교)'}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def collect(station, start, end, name):
    # 댐 관측소는 절대 수위를 제공하므로 눈금 기준 확인 지점만 이 경로로 수집한다.
    require(station in GAUGE_STATIONS, 'WAMIS_GAUGE_REFERENCE_UNVERIFIED')
    manifest_path = ROOT / 'data/manifests' / (name + '.json')
    directory = ROOT / 'data/raw' / name
    require(not manifest_path.exists() and not directory.exists(), 'WAMIS_ARCHIVE_EXISTS')
    params = {'code': station, 'date1': start, 'date2': end, 'name': ''}
    page = 'https://www.wamis.go.kr/wkw/wl_hrdata.do?' + urlencode({'code': station, 'name': 'Seoul'})
    endpoint = 'https://www.wamis.go.kr/wkw/wl_hrdata_list.do'
    headers = {'User-Agent': 'WATER-LEAGUE-public-data/1.0', 'Referer': page}
    resources = [('hourly.json', Request(endpoint, data=urlencode(params).encode(), headers=headers)),
                 ('hourly-page.html', Request(page, headers=headers)),
                 ('station-page.html', Request('https://www.wamis.go.kr/wkw/wl_obsinfo.do?code=' + station,
                                               headers=headers))]
    directory.mkdir(parents=True)
    for filename, request in resources:
        with urlopen(request, timeout=30) as response:
            raw = response.read(8 * 1024**2 + 1)
            require(len(raw) <= 8 * 1024**2, 'WAMIS_SOURCE_TOO_LARGE')
            (directory / filename).write_bytes(raw)
    normalized = normalize((directory / 'hourly.json').read_bytes(), station, start, end)
    write(directory / 'normalized.json', normalized)
    manifest = {'schemaVersion': 1, 'source': 'WAMIS_PUBLIC_HOURLY_TABLE', 'stationId': station,
        'sourceUrl': page, 'endpoint': endpoint, 'method': 'POST', 'parameters': params,
        'retrievedAt': datetime.now(timezone.utc).isoformat(),
        'sampleCount': normalized['sampleCount'], 'missingCount': normalized['missingCount'],
        'reference': normalized['reference'], 'sourceQuality': 'UNCORRECTED_PUBLIC_VALUE',
        'absoluteDatumVerified': False, 'rankingEligible': False,
        'normalizerSha256': hashlib.sha256((ROOT / 'simulation/waterleague_sim/ingestion/wamis_stage.py').read_bytes()).hexdigest(),
        'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(directory.iterdir()) if p.is_file()}}
    write(manifest_path, manifest)
    print(json.dumps({'manifest': str(manifest_path.relative_to(ROOT)),
                      'samples': normalized['sampleCount'], 'missing': normalized['missingCount']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--station', default='1018662', choices=GAUGE_STATIONS)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    require(args.name.replace('-', '').isalnum(), 'WAMIS_ARCHIVE_NAME_INVALID')
    collect(args.station, args.start, args.end, args.name)
