"""관측 당시 지점 좌표 수집. 인증 URL·키 저장 및 출력 금지."""
from local_config import ROOT, load
import sys
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.live import shared_response
from fetch_kma import NoRedirect
from urllib.request import build_opener
from urllib.parse import urlencode
from urllib.error import HTTPError
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import math


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--station', default='421')
    parser.add_argument('--time', required=True)
    args = parser.parse_args()
    if not (args.station.isdigit() and 1 <= len(args.station) <= 4):
        raise SystemExit('관측소 번호 오류')
    try:
        if len(args.time) != 12 or not args.time.isdigit():
            raise ValueError()
        datetime.strptime(args.time, '%Y%m%d%H%M')
    except ValueError:
        raise SystemExit('유효한 과거 시점 필요') from None
    load()
    key = os.environ.get('KMA_API_KEY')
    if not key:
        raise SystemExit('.env.local KMA_API_KEY 설정 필요')
    endpoint = 'https://apihub.kma.go.kr/api/typ01/url/stn_inf.php'
    params = {'inf': 'AWS', 'stn': args.station, 'tm': args.time, 'help': '1'}
    try:
        data, acquisition = shared_response(endpoint, params, key)
    except Exception:
        raise SystemExit('기상청 조회 불가 또는 공유 호출 한도 도달') from None
    if len(data) > 100000 or key.encode() in data or b'#START7777' not in data or b'#7777END' not in data:
        raise SystemExit('지점정보 응답 검사 실패')
    try:
        rows = [line.split() for line in data.decode('euc-kr').splitlines() if line.strip() and not line.startswith('#')]
        if len(rows) != 1 or rows[0][0] != args.station:
            raise ValueError()
        lon, lat, altitude = [float(rows[0][i]) for i in (1, 2, 4)]
        if not all(math.isfinite(v) for v in (lon, lat, altitude)) or not 124 < lon < 132 or not 33 < lat < 39:
            raise ValueError()
    except (ValueError, IndexError, UnicodeDecodeError):
        raise SystemExit('지점 좌표 형식 오류') from None
    stem = f'kma-station-{args.station}-{args.time}'
    raw = ROOT/'data/raw'/f'{stem}.txt'
    if raw.exists() and raw.read_bytes() != data:
        raise SystemExit('기존 원본과 응답 불일치; 덮어쓰기 중단')
    raw.write_bytes(data)
    manifest = {'endpoint': endpoint, 'parameters': params, 'sha256': hashlib.sha256(data).hexdigest(), 'retrievedOn': datetime.fromisoformat(acquisition['fetchedAt']).date().isoformat()}
    (ROOT/'data/manifests'/f'{stem}.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    evidence = {'stationId': args.station, 'requestedTimeKst': args.time, 'longitude': lon, 'latitude': lat, 'altitudeM': altitude, 'sourceSha256': manifest['sha256'], 'sourceUrl': 'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=317', 'historicalLocationStatus': 'API_TIME_QUERY_CONFIRMED', 'limitation': '요청 시점 API 조회 결과. 전체 이전 이력 또는 현장 실측 검증을 의미하지 않음'}
    (ROOT/'data/derived'/f'{stem}.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print('과거 지점정보 확인:', args.station, args.time, lon, lat, altitude)


if __name__ == '__main__':
    main()
