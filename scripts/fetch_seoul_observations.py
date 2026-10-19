"""공개 서울 관측 파일 수집. 기존 원본의 해시 변경 시 중단."""
import argparse
import hashlib
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from fetch_kma import NoRedirect
from local_config import ROOT

ENDPOINT = 'https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false'
SOURCES = {
    'rain': ('OA-22715', '3', '1', 'seoul-rain-2021-2024.zip', 35_000_000),
    'stations': ('OA-22824', '2', '1', 'seoul-rain-stations-20260915.xlsx', 2_000_000),
    'sewer': ('OA-2527', '17', '3', 'seoul-sewer-2024.zip', 800_000_000),
    'district-boundaries': ('OA-22161', '1', '3', 'seoul-district-boundaries-20231031.zip', 2_000_000),
}


def fetch(name):
    code, sequence, inf_sequence, filename, limit = SOURCES[name]
    path = ROOT / 'data/raw' / filename
    manifest_path = ROOT / 'data/manifests' / (filename + '.json')
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if path.exists():
        with path.open('rb') as stream:
            valid = existing and hashlib.file_digest(stream, 'sha256').hexdigest() == existing['sha256']
        if not valid:
            raise SystemExit('기존 원본·manifest 해시 불일치')
        print(filename, '기존 원본 해시 확인')
        return
    params = {'infId': code, 'seqNo': '', 'seq': sequence, 'infSeq': inf_sequence}
    page = f'https://data.seoul.go.kr/dataList/{code}/F/1/datasetView.do'
    request = Request(ENDPOINT, data=urlencode(params).encode(), headers={'Referer': page})
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < limit + 512_000_000:
        raise SystemExit('서울 관측 원본 수집 여유 공간 부족')
    temporary = None
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            size, hasher = 0, hashlib.sha256()
            started = last_log = time.monotonic()
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.part', delete=False) as stream:
                temporary = Path(stream.name)
                while chunk := response.read(1024 * 1024):
                    if not size and not chunk.startswith(b'PK\x03\x04'):
                        raise ValueError('ZIP 형식 오류')
                    size += len(chunk)
                    if size > limit or time.monotonic() - started > 900:
                        raise ValueError('크기·시간 제한 초과')
                    stream.write(chunk)
                    hasher.update(chunk)
                    if time.monotonic() - last_log >= 10:
                        print(filename, round(size / 1024 / 1024, 1), 'MiB 수집', flush=True)
                        last_log = time.monotonic()
                if not size:
                    raise ValueError('빈 응답')
            digest = hasher.hexdigest()
            if existing and existing['sha256'] != digest:
                raise ValueError('제공 원본 해시 변경')
            temporary.replace(path)
    except Exception:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise SystemExit('서울 관측 다운로드·형식·크기·해시 검사 실패; 기존 원본 유지') from None
    if not existing:
        manifest = {'provider': '서울특별시', 'sourcePage': page, 'endpoint': ENDPOINT,
                    'method': 'POST', 'parameters': params, 'filename': filename,
                    'sha256': digest, 'bytes': size,
                    'acquiredAt': datetime.now(timezone.utc).isoformat()}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(filename, size, 'bytes', digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', choices=(*SOURCES, 'all'), default='all', nargs='?')
    args = parser.parse_args()
    for name in SOURCES if args.source == 'all' else [args.source]:
        fetch(name)
