"""외부 관측 요청 공유와 공급자별 API·워커 공통 일일 호출 예산."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[3]
# 공급자 상한의 10%를 남겨 수동 조회·다른 프로세스의 미집계 요청에 대비한다.
MAX_CALLS = 18000
MAX_BYTES = 4_500_000_000
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS budget(account TEXT,day TEXT,calls INTEGER NOT NULL,bytes INTEGER NOT NULL,blocked_until REAL NOT NULL,PRIMARY KEY(account,day))',
    'CREATE TABLE IF NOT EXISTS responses(account TEXT,id TEXT,raw BLOB,sha TEXT,fetched REAL,expires REAL,lease TEXT,lease_until REAL,PRIMARY KEY(account,id))',
)


class RequestBlocked(ValueError):
    pass


def location():
    root = Path(os.environ.get('EXTERNAL_REQUEST_STATE_DIR', ROOT/'data/private/external-requests'))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise RequestBlocked('KMA_REQUEST_STATE_INVALID')
    return root/'requests.sqlite3'


@contextmanager
def database():
    path = location()
    if path.is_symlink():
        raise RequestBlocked('KMA_REQUEST_STATE_INVALID')
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        db.execute('PRAGMA busy_timeout=10000')
        for sql in SCHEMA:
            db.execute(sql)
        yield db
    finally:
        db.close()


def identity(key, provider='KMA'):
    return hashlib.sha256((provider+'\n'+key).encode()).hexdigest()


def period(now):
    at = datetime.fromtimestamp(now, KST)
    return at.date().isoformat(), (at.replace(hour=0, minute=0, second=0, microsecond=0)+timedelta(days=1)).timestamp()


def reserve(key, maximum, now=None, provider='KMA', max_calls=MAX_CALLS, max_bytes=MAX_BYTES):
    now = time.time() if now is None else now
    day, _ = period(now)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO budget VALUES(?,?,0,0,0)', (identity(key,provider), day))
        calls, size = db.execute('SELECT calls,bytes FROM budget WHERE account=? AND day=?', (identity(key,provider),day)).fetchone()
        blocked = db.execute('SELECT COALESCE(MAX(blocked_until),0) FROM budget WHERE account=?', (identity(key,provider),)).fetchone()[0]
        if blocked > now or calls >= max_calls or size+maximum > max_bytes:
            db.rollback()
            raise RequestBlocked('KMA_REQUEST_BUDGET_BLOCKED')
        db.execute('UPDATE budget SET calls=calls+1,bytes=bytes+? WHERE account=? AND day=?', (maximum,identity(key,provider),day))
        db.commit()
    return day


def settle(key, day, maximum, actual, provider='KMA'):
    with database() as db:
        db.execute('UPDATE budget SET bytes=bytes-? WHERE account=? AND day=?', (max(0,maximum-actual),identity(key,provider),day))


def block(key, status=None, retry_seconds=60, now=None, provider='KMA'):
    now = time.time() if now is None else now
    day, midnight = period(now)
    until = midnight if status in (401,403) else now+max(60,retry_seconds)
    with database() as db:
        db.execute('INSERT OR IGNORE INTO budget VALUES(?,?,0,0,0)',(identity(key,provider),day))
        db.execute('UPDATE budget SET blocked_until=MAX(blocked_until,?) WHERE account=? AND day=?',(until,identity(key,provider),day))


def acquire(endpoint, parameters, key, loader, heartbeat=None, ttl=86400, provider='KMA'):
    request_id = hashlib.sha256((endpoint+'\n'+json.dumps(parameters,sort_keys=True,separators=(',',':'))).encode()).hexdigest()
    account, token, deadline = identity(key,provider), str(uuid.uuid4()), time.monotonic()+75
    while True:
        if heartbeat: heartbeat()
        now = time.time()
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT raw,sha,fetched,expires,lease_until FROM responses WHERE account=? AND id=?',(account,request_id)).fetchone()
            if row and row[0] is not None and row[3] > now:
                if hashlib.sha256(row[0]).hexdigest()!=row[1]:
                    raise RequestBlocked('KMA_RESPONSE_CACHE_INVALID')
                db.commit()
                return row[0], {'fetchedAt':datetime.fromtimestamp(row[2],timezone.utc).isoformat(),'sharedResponse':True}
            if not row or not row[4] or row[4] < now:
                db.execute('INSERT INTO responses(account,id,lease,lease_until) VALUES(?,?,?,?) ON CONFLICT(account,id) DO UPDATE SET lease=excluded.lease,lease_until=excluded.lease_until', (account,request_id,token,now+75))
                db.commit()
                break
            db.commit()
        if time.monotonic()>=deadline:
            raise RequestBlocked('KMA_REQUEST_IN_PROGRESS')
        time.sleep(.2)
    try:
        raw = loader()
        fetched = time.time()
        # 절대 시각의 동일 요청만 재사용하며 현재 시각으로 옮기거나 실패 자료를 저장하지 않는다.
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM responses WHERE (expires<? OR expires IS NULL) AND (lease_until IS NULL OR lease_until<?)',(fetched,fetched))
            size = db.execute('SELECT COALESCE(SUM(length(raw)),0) FROM responses').fetchone()[0]
            while size+len(raw)>512_000_000:
                old = db.execute('SELECT account,id,length(raw) FROM responses WHERE raw IS NOT NULL AND (lease_until IS NULL OR lease_until<?) ORDER BY fetched LIMIT 1',(fetched,)).fetchone()
                if not old: break
                db.execute('DELETE FROM responses WHERE account=? AND id=?',old[:2])
                size-=old[2]
            db.execute('UPDATE responses SET raw=?,sha=?,fetched=?,expires=?,lease=NULL,lease_until=NULL WHERE account=? AND id=? AND lease=?',(raw,hashlib.sha256(raw).hexdigest(),fetched,fetched+ttl,account,request_id,token))
            db.commit()
        return raw, {'fetchedAt':datetime.fromtimestamp(fetched,timezone.utc).isoformat(),'sharedResponse':False}
    finally:
        with database() as db:
            db.execute('UPDATE responses SET lease=NULL,lease_until=NULL WHERE account=? AND id=? AND lease=?',(account,request_id,token))


def available(key, now=None):
    if not key: return False
    now = time.time() if now is None else now
    day, _ = period(now)
    try:
        with database() as db:
            row = db.execute('SELECT calls,bytes FROM budget WHERE account=? AND day=?', (identity(key),day)).fetchone()
            blocked = db.execute('SELECT COALESCE(MAX(blocked_until),0) FROM budget WHERE account=?', (identity(key),)).fetchone()[0]
        return blocked <= now and (row is None or (row[0] < MAX_CALLS and row[1]+4_000_000 <= MAX_BYTES))
    except (OSError, sqlite3.Error, RequestBlocked):
        return False


def response_ttl(parameters):
    value = parameters.get('tm2') or parameters.get('tm')
    try:
        end = datetime.strptime(value, '%Y%m%d%H%M').replace(tzinfo=KST)
        return 60 if datetime.now(KST)-end < timedelta(hours=2) else 86400
    except (ValueError, TypeError):
        return 86400
