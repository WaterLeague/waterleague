"""공개 서울 관측 파일 수집. 기존 원본의 해시 변경 시 중단."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from fetch_kma import NoRedirect
from local_config import ROOT

ENDPOINT = 'https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false'
SOURCES = {
    'rain': ('OA-22715', '3', 'seoul-rain-2021-2024.zip', 35_000_000),
    'stations': ('OA-22824', '2', 'seoul-rain-stations-20260915.xlsx', 2_000_000),
}


def fetch(name):
    code, sequence, filename, limit = SOURCES[name]
    path = ROOT / 'data/raw' / filename
    manifest_path = ROOT / 'data/manifests' / (filename + '.json')
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if path.exists():
        if not existing or hashlib.sha256(path.read_bytes()).hexdigest() != existing['sha256']:
            raise SystemExit('기존 원본·manifest 해시 불일치')
        print(filename, '기존 원본 해시 확인')
        return
    params = {'infId': code, 'seqNo': '', 'seq': sequence, 'infSeq': '1'}
    page = f'https://data.seoul.go.kr/dataList/{code}/F/1/datasetView.do'
    request = Request(ENDPOINT, data=urlencode(params).encode(), headers={'Referer': page})
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            data = response.read(limit + 1)
    except Exception:
        raise SystemExit('서울 관측 원본 다운로드 실패') from None
    if len(data) > limit or not data.startswith(b'PK\x03\x04'):
        raise SystemExit('서울 관측 원본 크기·파일 형식 오류')
    digest = hashlib.sha256(data).hexdigest()
    if existing and existing['sha256'] != digest:
        raise SystemExit('서울 관측 제공 원본 해시 변경; 덮어쓰기 중단')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_bytes(data)
    temporary.replace(path)
    if not existing:
        manifest = {'provider': '서울특별시', 'sourcePage': page, 'endpoint': ENDPOINT,
                    'method': 'POST', 'parameters': params, 'filename': filename,
                    'sha256': digest, 'bytes': len(data),
                    'acquiredAt': datetime.now(timezone.utc).isoformat()}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(filename, len(data), 'bytes', digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', choices=(*SOURCES, 'all'), default='all', nargs='?')
    args = parser.parse_args()
    for name in SOURCES if args.source == 'all' else [args.source]:
        fetch(name)
