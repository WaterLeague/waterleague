"""설치 당시 공개 경계 정책의 원본을 재현 묶음에 고정."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICIES = {
    'seoul-infrastructure-occupancy-20261019-v5': '5271ba50b87d0de090a6fdf5128c2e383ab67238b98d326e99abf1852d99af1a',
    'seoul-basin-footprints-20261018-v4': '5b15ba1ff3df4460f33a4bac3dd68485c082d7c56d75eec8653d8631444eb871',
    'seoul-basin-footprints-20261018-v3': '4937ca34cfeb59441ea80c539863f8359207e6ad27af7c227e600af523463d16',
    'seoul-basin-footprints-20261018-v2': '42595f660fa135279a87488c5cafe872326884562312d123394d5b197e93c3a0',
    'seoul-basin-footprints-20261018-v1':
        '65faea2a057d5aeb2a05b5ca2d09b2b962aa3888cfd615fb898119006cf7ec4c',
}


def archive(policy, directory):
    if policy is None:
        return
    version = policy.get('version')
    expected = POLICIES.get(version)
    if expected is None or expected != policy.get('sha256'):
        raise ValueError('INSTALLATION_POLICY_INVALID')
    raw = (ROOT/'backend/src/main/resources/infrastructure'/f'{version}.json').read_bytes()
    source = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != expected
            or source.get('version') != version
            or any(source.get(k) != policy.get(k) for k in
                   ('sourceSha256', 'scope', 'historicalExistenceVerified'))):
        raise ValueError('INSTALLATION_POLICY_SOURCE_INVALID')
    # 새 정책을 이전 기록에 덧씌우지 않고 저장된 버전의 경계·교차 근거를 보존한다.
    (directory/'public-asset-policy.json').write_bytes(raw)
    (directory/'admission.py').write_bytes(Path(__file__).read_bytes())
