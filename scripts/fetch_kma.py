"""승인된 기상청 AWS 매분자료 수집. 인증 URL과 키 출력 금지."""
from local_config import ROOT, load
import sys
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.live import shared_response
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError
from datetime import datetime, timezone
import os
import json
import hashlib
import argparse


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    load()
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='202407180500')
    parser.add_argument('--end', default='202407182359')
    parser.add_argument('--station', default='108')
    args = parser.parse_args()
    if not (args.station.isdigit() and 1 <= len(args.station) <= 4):
        raise SystemExit('관측소 번호 오류')
    try:
        if any(len(x) != 12 or not x.isdigit() for x in (args.start, args.end)):
            raise ValueError()
        start, end = [datetime.strptime(x, '%Y%m%d%H%M') for x in (args.start, args.end)]
        if not (0 < (end-start).total_seconds() <= 86400):
            raise ValueError()
    except ValueError:
        raise SystemExit('최대 하루의 유효한 시간 범위 필요') from None
    key = os.environ.get('KMA_API_KEY')
    if not key:
        raise SystemExit('.env.local KMA_API_KEY 설정 필요')
    base = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'
    params = {'tm1': args.start, 'tm2': args.end, 'stn': args.station, 'disp': '0', 'help': '1'}
    try:
        data, acquisition = shared_response(base, params, key)
    except Exception:
        raise SystemExit('기상청 조회 불가 또는 공유 호출 한도 도달') from None
    if len(data) > 4000000 or b'#START7777' not in data or b'#7777END' not in data:
        raise SystemExit('응답 형식·길이 검사 실패')
    if key.encode() in data:
        raise SystemExit('응답에 비밀값 포함; 저장 중단')
    prefix = f'kma-{args.station}-{args.start}-{args.end}'
    out = ROOT/'data/raw'/f'{prefix}.txt'
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(data)
    manifest = {'provider': '기상청', 'endpoint': base, 'parameters': params,
                'acquiredAt': acquisition['fetchedAt'],
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                'sourceTimezone': 'Asia/Seoul',
                'sourceNotice': 'AWS 원본의 -50 이하 값은 결측·오류. 별도 품질 플래그 미포함.'}
    (ROOT/'data/manifests'/f'{prefix}.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print('기상청 원본 저장:', out.name, '바이트:', len(data))


if __name__ == '__main__':
    main()
