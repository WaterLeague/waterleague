"""공식 공개 첨부파일의 고정 버전을 프로젝트에 보관."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'data/manifests/seoul-biotope-20261018.json'


def acquire():
    manifest = json.loads(MANIFEST.read_bytes())
    for row in manifest['files']:
        url = urlsplit(row['url'])
        if url.scheme != 'https' or url.netloc != 'seoulboard.seoul.go.kr' or url.path != '/comm/getFile':
            raise ValueError('등록 공식 첨부 경로 필요')
        path = (ROOT / row['file']).resolve()
        if not path.is_relative_to(ROOT / 'data/private/seoul-biotope-20261018'):
            raise ValueError('원본 저장 경로 오류')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + '.part')
            with urlopen(Request(row['url'], headers={'User-Agent': 'WATER-LEAGUE-public-data/1.0',
                         'Referer': 'https://urban.seoul.go.kr/'}), timeout=45) as response:
                if urlsplit(response.geturl()).hostname != 'seoulboard.seoul.go.kr':
                    raise ValueError('등록 첨부 외부 이동 거부')
                with temporary.open('xb') as stream:
                    count = 0
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > row['bytes']:
                            raise ValueError('등록 원본 크기 초과')
                        stream.write(chunk)
            if temporary.stat().st_size != row['bytes'] or hashlib.sha256(temporary.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('첨부 버전 불일치: 부분 파일 보존')
            temporary.rename(path)
        if path.stat().st_size != row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('보관 원본 해시 불일치')
        print(row['year'], path.name, row['bytes'], row['sha256'], flush=True)


if __name__ == '__main__':
    acquire()
