"""고유 Compose 프로젝트에서 HTTPS·권한·실제 SWMM·재시작 검증 후 자체 리소스만 정리."""
import base64
import hashlib
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(state):
    if os.getuid() == 0:
        raise ValueError('비root 사용자로 실행 필요')
    os.chmod(state, 0o700)
    for name in ('secrets', 'artifacts', 'cache', 'caddy-data', 'caddy-config'):
        (state / name).mkdir(mode=0o700)
    values = {role + '-password': secrets.token_urlsafe(36)
              for role in ('wl_admin', 'wl_owner', 'wl_api', 'wl_worker')}
    values['mfa-key'] = base64.b64encode(secrets.token_bytes(32)).decode()
    values['database-url'] = 'postgresql://wl_worker:' + values['wl_worker-password'] + '@db:5432/waterleague'
    for name, value in values.items():
        path = state / 'secrets' / name
        path.write_text(value)
        path.chmod(0o600)
    return list(values.values())


class Stack:
    def __init__(self, state, hidden):
        self.project = 'wlcheck-' + uuid.uuid4().hex[:12]
        self.hidden = hidden
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.env = os.environ | {
            'WL_PROJECT': self.project, 'WL_STATE_DIR': str(state),
            'WL_RUNTIME_UID': str(os.getuid()), 'WL_RUNTIME_GID': str(os.getgid()),
            'WL_HTTPS_PORT': str(self.port), 'COMPOSE_DISABLE_ENV_FILE': '1',
        }
        self.command = ['docker', 'compose', '-f', str(ROOT / 'deploy/compose.yml'), '-p', self.project]

    def safe(self, value):
        for secret in self.hidden:
            value = value.replace(secret, '[REDACTED]')
        return value

    def run(self, *args, input=None, timeout=300, check=True):
        result = subprocess.run([*self.command, *args], cwd=ROOT, env=self.env, input=input,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            print(self.safe(result.stdout[-12000:]), file=sys.stderr)
            raise RuntimeError('CONTAINER_COMMAND_FAILED: ' + args[0])
        return result

    def python(self, service, source):
        return self.run('exec', '-T', service, 'python', '-', input=source).stdout

    def inspect(self, service):
        cid = self.run('ps', '-q', service).stdout.strip()
        result = subprocess.run(['docker', 'inspect', cid], check=True, text=True, capture_output=True)
        return json.loads(result.stdout)[0]


def check_permissions(stack):
    source = """
import sys
sys.path.insert(0, '/app/deploy')
from database import connect
import psycopg
for role in ('wl_api', 'wl_worker'):
    with connect(role) as db:
        denied = ['CREATE TABLE denied_probe(id int)', 'CREATE ROLE denied_probe',
                  'SELECT * FROM flyway_schema_history', 'TRUNCATE simulation_jobs']
        if role == 'wl_worker':
            denied += ['SELECT * FROM accounts', 'SELECT * FROM account_mfa',
                       'SELECT * FROM research_consents', 'SELECT events FROM strategy_versions',
                       "UPDATE research_candidates SET placements='[]' WHERE false",
                       "UPDATE simulation_jobs SET input_hash='changed' WHERE false",
                       'DELETE FROM simulation_jobs WHERE false',
                       'SELECT * FROM budget_ledger_entries',
                       'SELECT * FROM historical_design_revisions',
                       "UPDATE watershed_experiments SET placements='[]' WHERE false",
                       "UPDATE historical_submissions SET rules_hash='changed' WHERE false",
                       "UPDATE shared_weekly_scores SET rule_version='changed' WHERE false",
                       'UPDATE accounts SET enabled=false WHERE false']
        for statement in denied:
            try:
                with db.transaction():
                    db.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                continue
            raise AssertionError('DB_PERMISSION_NOT_DENIED')
        with db.transaction(force_rollback=True):
            db.execute('SELECT id FROM queue_admission WHERE id=1 FOR UPDATE')
            db.execute('SELECT id,placements FROM strategy_versions LIMIT 1')
            db.execute("UPDATE simulation_jobs SET state='FAILED',result=NULL WHERE false")
            db.execute("UPDATE research_candidates SET state='FAILED',result=NULL WHERE false")
            db.execute("UPDATE watershed_experiments SET state='FAILED',result=NULL WHERE false")
            if role == 'wl_worker':
                db.execute('UPDATE historical_submissions SET difference_m3=0 WHERE false')
                db.execute('UPDATE shared_weekly_scores SET evaluated_seconds=1 WHERE false')
        flags = db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        assert not any(flags)
print('DB_PERMISSIONS_OK')
"""
    result = stack.run('run', '--rm', '--no-deps', '-T', 'bootstrap', 'python', '-', input=source)
    assert 'DB_PERMISSIONS_OK' in result.stdout


def check_isolation(stack):
    for service in ('api', 'worker', 'web'):
        item = stack.inspect(service)
        host = item['HostConfig']
        assert item['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
        assert host['ReadonlyRootfs'] and host['CapDrop'] == ['ALL']
        assert 'no-new-privileges:true' in host['SecurityOpt']
        assert host['Memory'] > 0 and host['NanoCpus'] > 0 and host['PidsLimit'] > 0
        assert all('PASSWORD=' not in value and 'DATABASE_URL=' not in value and 'MFA_ENCRYPTION_KEY=' not in value
                   for value in item['Config']['Env'])
        if service != 'web':
            assert not host['PortBindings']
        else:
            assert all(p['HostIp'] == '127.0.0.1' for ports in host['PortBindings'].values() for p in ports)
    assert not stack.inspect('db')['HostConfig']['PortBindings']
    mounts = {m['Destination']: m for m in stack.inspect('api')['Mounts']}
    assert mounts['/artifacts']['RW'] is False
    networks = stack.inspect('worker')['NetworkSettings']['Networks']
    assert len(networks) == 1
    result = subprocess.run(['docker', 'network', 'inspect', next(iter(networks))], check=True,
                            text=True, capture_output=True)
    assert json.loads(result.stdout)[0]['Internal'] is True
    assert 'ISOLATION_OK' in stack.python('worker', """
import os, pathlib, socket
assert os.getuid() != 0
try:
    pathlib.Path('/app/write-test').write_text('denied')
except OSError:
    pass
else:
    raise AssertionError('ROOT_WRITABLE')
try:
    connection = socket.create_connection(('1.1.1.1', 443), timeout=3)
except OSError:
    pass
else:
    connection.close()
    raise AssertionError('WORKER_EGRESS_ALLOWED')
print('ISOLATION_OK')
""")


class Client:
    def __init__(self, base, ca):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))))

    def call(self, path, body=None, token=None, expected=200, headers=None):
        hdr = {'Content-Type': 'application/json'} | (headers or {})
        if token:
            hdr['X-CSRF-TOKEN'] = token
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=hdr)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            if response.status != expected:
                raise AssertionError(f'HTTP_STATUS {path} {response.status} != {expected}')
            return raw, response.headers

    def api(self, path, body=None, expected=200):
        token = self.api('/auth/csrf')['token'] if body is not None else None
        raw, headers = self.call('/api/v1' + path, body, token, expected)
        assert 'no-store' in headers['Cache-Control']
        return json.loads(raw) if raw else None


def check_http(stack, state):
    ca = state / 'caddy-data/caddy/pki/authorities/local/root.crt'
    assert ca.is_file()
    client = Client(f'https://localhost:{stack.port}', ca)
    page, headers = client.call('/')
    assert 'text/html' in headers['Content-Type']
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Cache-Control'] == 'no-cache'
    assert headers['Strict-Transport-Security'] and not headers.get('Server')
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.decode())
    assert assets
    for asset in assets:
        raw, headers = client.call(asset)
        assert raw and 'immutable' in headers['Cache-Control']
    for path in ('/.env.local', '/.git/config', '/actuator/health', '/assets/absent.js'):
        client.call(path, expected=404)
    client.api('/auth/me', expected=401)
    spatial = client.api('/spatial/play')
    assert spatial['catalogSha256'] == '4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7'
    assert spatial['coordinateSystem'] == 'EPSG:5186'
    query = '/spatial/play/sites?minx=203899.54225604248&miny=551377.4775&maxx=204049.54225604248&maxy=551527.4775&districtId=11200'
    native = client.api(query)
    assert native['catalogSha256'] == spatial['catalogSha256'] and len(native['sites']) == 162
    cell = native['sites'][0]
    single = client.api('/spatial/play/sites/11200/' + cell['id'])
    assert single['site'] == cell and cell['geometryCrs'] == 'EPSG:5186'
    worker_native = json.loads(stack.python('worker', """
import json
from waterleague_sim.spatial.play_bundle import open_catalog
catalog = open_catalog()
cells = catalog.bounds([203899.54225604248, 551377.4775, 204049.54225604248, 551527.4775], district='11200')
print(json.dumps({'catalogSha256': catalog.sha256, 'sites': cells}))
"""))
    assert worker_native == {key: native[key] for key in ('catalogSha256', 'sites')}
    registry = client.api('/spatial/play/forcings')
    assert registry['catalog']['siteCatalogSha256'] == spatial['catalogSha256']
    assert len(registry['catalog']['regions']) == 25 and len(registry['catalog']['models']) == 100
    forcing = {entry['sha256']: client.api('/spatial/play/forcings/' + entry['sha256'])
               for entry in registry['catalog']['models']}
    worker_forcing = json.loads(stack.python('worker', """
import json
from waterleague_sim.spatial import game_catalog
values = {entry['sha256']: json.loads(game_catalog.forcing(entry['sha256']))
          for entry in game_catalog.catalog()['models']}
for checksum, value in values.items():
    if 'disasterEvent' in value:
        game_catalog.climate_binding('antecedent', checksum)
        game_catalog.climate_binding('evaporation', checksum)
print(json.dumps({'catalogSha256': game_catalog.SHA256, 'forcings': values}))
"""))
    assert worker_forcing == {'catalogSha256': registry['catalogSha256'], 'forcings': forcing}
    assert client.api('/spatial/play/forcings/invalid', expected=400)['code'] == 'REQUEST_INVALID'
    assert client.api('/spatial/play/forcings/' + '0' * 64, expected=422)['code'] == 'MODEL_NOT_ELIGIBLE'
    assert client.api(query + '&limit=1', expected=422)['code'] == 'SPATIAL_VIEW_TOO_DENSE'
    client.api('/spatial/play/sites?minx=0&miny=0&maxx=2001&maxy=1', expected=400)
    client.call('/api/v1/auth/register', {}, expected=403)
    _, headers = client.call('/api/v1/auth/csrf', headers={
        'Forwarded': 'proto=http;host=attacker.example', 'X-Forwarded-Proto': 'http',
        'X-Forwarded-For': '198.51.100.1', 'X-Forwarded-Host': 'attacker.example',
        'X-Forwarded-Port': '80', 'X-Forwarded-Prefix': '/forged'})
    assert headers.get('Strict-Transport-Security')
    name, password = 'tls_' + uuid.uuid4().hex[:12], secrets.token_urlsafe(24)
    member = client.api('/auth/register', {'username': name, 'password': password, 'memberType': 'PLAYER', 'districtId': '2410520', 'affiliationType': 'AFFILIATED',
                                         'organizationName': '', 'purpose': ''})
    cookies = [c for c in client.cookies if c.name == '__Host-waterleague']
    assert len(cookies) == 1
    cookie = cookies[0]
    assert cookie.secure and cookie.path == '/' and not cookie.domain_specified
    assert cookie.has_nonstandard_attr('HttpOnly')
    assert cookie.get_nonstandard_attr('SameSite').lower() == 'lax'
    client.api('/auth/logout', {})
    client.api('/auth/me', expected=401)
    client.api('/auth/login', {'username': name, 'password': password})
    client.api('/research/strategies', expected=403)
    model = client.api('/lab')
    assert model['model']['validationLevel'] == 'EXPLORATORY'
    version = client.api('/strategies', {'title': '컨테이너 검증', 'modelHash': model['modelHash'],
        'placements': [{'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20}],
        'designNote': '격리 환경의 실제 SWMM 계산 검증', 'baseRevision': 0})
    job = client.api('/simulations', {'versionId': version['id'], 'requestKey': str(uuid.uuid4())}, 202)
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        job = client.api('/simulations/' + job['id'])
        if job['state'] not in ('RUNNING', 'QUEUED'):
            break
        time.sleep(2)
    assert job['state'] == 'SUCCEEDED', job.get('errorCode')
    bundle, headers = client.call('/api/v1/simulations/' + job['id'] + '/bundle')
    assert headers['Content-Type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = archive.namelist()
        assert len(set(names)) == len(names)
        manifest = json.loads(archive.read('manifest.json'))
        # API가 내보낸 바이트를 다시 해시하여 파일 사본과 계산 입력의 연결 검증.
        assert len(manifest) == 18
        for name, digest in manifest.items():
            raw = archive.read(name)
            assert hashlib.sha256(raw).hexdigest() == digest
        assert hashlib.sha256(archive.read('model-source.json')).hexdigest() == model['modelHash']
    artifact = state / 'artifacts' / job['id'] / job['result']['artifactToken']
    assert (artifact / 'manifest.json').is_file()
    rerun = """
import json, pathlib, tempfile
from waterleague_sim.result_cache import decoded, execute
source = pathlib.Path(ARTIFACT)
with tempfile.TemporaryDirectory() as directory:
    target = pathlib.Path(directory)
    for name in ('model-source.json', 'request.json'):
        (target/name).write_bytes((source/name).read_bytes())
    execute((source/'model-source.json').read_bytes(), decoded((source/'request.json').read_bytes()), target, None)
    before = json.loads((source/'result.json').read_text())
    after = json.loads((target/'result.json').read_text())
    assert before == after
print('SWMM_REPLAY_OK')
""".replace('ARTIFACT', repr('/artifacts/' + job['id'] + '/' + job['result']['artifactToken']))
    assert 'SWMM_REPLAY_OK' in stack.python('worker', rerun)
    stack.run('restart', 'db', 'api', 'worker', timeout=180)
    stack.run('up', '-d', '--wait', '--wait-timeout', '120', 'api', 'worker', 'web', timeout=240)
    assert client.api('/auth/me') == member
    assert client.api('/simulations/' + job['id']) == job
    repeated, _ = client.call('/api/v1/simulations/' + job['id'] + '/bundle')
    with zipfile.ZipFile(io.BytesIO(repeated)) as archive:
        assert json.loads(archive.read('manifest.json')) == manifest
    return {'jobState': job['state'], 'manifestFiles': len(manifest), 'modelHash': model['modelHash'],
            'realSwmmReplay': True, 'restartPersistence': True, 'tlsVerified': True,
            'nativeApiWorkerCellsMatched': len(native['sites']), 'nativeCatalogSha256': spatial['catalogSha256'],
            'nativeApiWorkerForcingsMatched': len(forcing), 'nativeForcingCatalogSha256': registry['catalogSha256']}


def main():
    os.umask(0o077)
    subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True, timeout=15,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='container-check-', dir=ROOT / 'tmp') as directory:
        state = Path(directory)
        stack = Stack(state, prepare(state))
        clean = False
        try:
            print('컨테이너 이미지 빌드 시작', flush=True)
            stack.run('build', '--pull', timeout=1800)
            print('격리 DB 초기화·HTTPS 시작', flush=True)
            stack.run('up', '-d', '--wait', '--wait-timeout', '180', timeout=360)
            check_permissions(stack)
            check_isolation(stack)
            print('DB 권한·격리 확인, HTTPS 계산·재현 검증 시작', flush=True)
            report = check_http(stack, state)
            print(json.dumps(report, ensure_ascii=False), flush=True)
        except Exception:
            logs = stack.run('logs', '--no-color', '--tail', '50', check=False)
            print(stack.safe(logs.stdout[-16000:]), file=sys.stderr)
            raise
        finally:
            stack.run('down', '--volumes', '--remove-orphans', timeout=180)
            for service in ('api', 'worker', 'web'):
                subprocess.run(['docker', 'image', 'rm', stack.project + '-' + service + ':local'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            clean = True
            # 생성한 고유 Compose 프로젝트 외에는 prune/삭제를 수행하지 않음.
            print('격리 컨테이너·볼륨·임시 비밀 정리 완료', flush=True)
        assert clean


if __name__ == '__main__':
    main()
