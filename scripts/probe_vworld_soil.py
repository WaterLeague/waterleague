"""고정 성수 영역의 토양 API 접근 확인. 공간 원본·인증 URL 보관 금지."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from local_config import ROOT, load
from probe_vworld import NoRedirect

LAYERS = [
    ('LT_C_ASITSOILDRA', '배수등급', 'asitsoildra'),
    ('LT_C_ASITSOILDEP', '유효토심', 'asitsoildep'),
    ('LT_C_ASITDEEPSOIL', '심토토성', 'asitdeepsoil'),
    ('LT_C_GIMSSCS', '토양도', 'gimsscs'),
]
BBOX = [127.0525, 37.5430, 127.0555, 37.5455]


def main():
    load()
    key = os.environ.get('VWORLD_API_KEY', '')
    domain = os.environ.get('VWORLD_DOMAIN', 'http://127.0.0.1:5173').strip()
    parsed = urlsplit(domain)
    if not key or parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or len(domain) > 256 or any(c.isspace() for c in domain):
        raise SystemExit('기존 .env.local의 브이월드 키·등록 주소 확인 필요')
    records = []
    for layer, title, reference in LAYERS:
        parameters = {'service': 'data', 'version': '2.0', 'request': 'GetFeature', 'data': layer,
                      'geomFilter': 'BOX(' + ','.join(map(str, BBOX)) + ')', 'size': '10',
                      'page': '1', 'format': 'json', 'crs': 'EPSG:4326', 'key': key, 'domain': domain}
        try:
            request = Request('https://api.vworld.kr/req/data?' + urlencode(parameters), headers={'Referer': domain + '/'})
            with build_opener(NoRedirect).open(request, timeout=30) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000 or key.encode() in raw:
                raise ValueError('응답 검사 실패')
            response = json.loads(raw)['response']
            status = response['status']
            if status not in ('OK', 'NOT_FOUND'):
                raise ValueError('API 조회 거부')
            features = response.get('result', {}).get('featureCollection', {}).get('features', [])
            current = int(response['record']['current'])
            total = int(response['record']['total'])
            if current != len(features) or not 0 <= current <= total or current > 10:
                raise ValueError('응답 건수 불일치')
            fields = {name for f in features for name in f['properties']}
            allowed_fields = {'code_dc', 'code_ad', 'code_st', 'label'} if reference != 'gimsscs' else None
            if allowed_fields is not None and not fields <= allowed_fields:
                raise ValueError('예상하지 않은 속성')
            # 형상·속성값 대신 공개 스키마와 조회 건수만 감사 기록에 남긴다.
            records.append({'layer': layer, 'title': title, 'status': status, 'total': total,
                            'returned': current, 'completeResponse': total == current,
                            'attributeNames': sorted(fields),
                            'geometryTypes': sorted({f['geometry']['type'] for f in features}),
                            'referenceUrl': 'https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=' + reference + '&apiVer=2'})
        except HTTPError as error:
            raise SystemExit('브이월드 HTTP ' + str(error.code)) from None
        except (OSError, ValueError, KeyError, TypeError):
            raise SystemExit('브이월드 토양 조회 또는 응답 검사 실패') from None
    report = {'schemaVersion': 1, 'checkedAt': datetime.now(timezone.utc).isoformat(),
              'bbox': BBOX, 'crs': 'EPSG:4326', 'endpoint': 'https://api.vworld.kr/req/data',
              'layers': records, 'spatialRawSaved': False, 'includedInHydrology': False,
              'additionalKeyRequired': False, 'script': 'scripts/probe_vworld_soil.py',
              'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limitations': ['조회 성공은 원자료 저장·재배포 허락이 아님',
                              'API 갱신일은 토양 조사 시점의 증명이 아님',
                              '등급·토성·토심만으로 현장 침투율·지하수위·성토 상태 확정 불가',
                              '도시 포장 아래 원지반 및 실제 배수유역 대표성 미검증']}
    output = ROOT / 'data/manifests/vworld-soil-access-audit.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('토양 API 접근 점검 완료. 공간 원본 보관 없음:', ', '.join(f'{r["title"]} {r["returned"]}/{r["total"]}' for r in records))


if __name__ == '__main__':
    main()
