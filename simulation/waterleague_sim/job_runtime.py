"""작업 프로세스의 만료·중단 정리와 크기 제한 결과 읽기."""
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
import time


def run_process(command, *, env, timeout, heartbeat=None, heartbeat_interval=30):
    if (not math.isfinite(timeout) or timeout <= 0
            or not math.isfinite(heartbeat_interval) or heartbeat_interval <= 0):
        raise ValueError('WORKER_TIMEOUT_INVALID')
    if heartbeat is not None:
        heartbeat()
    child = None
    completed = False
    previous = None
    pending_signal = None
    signals = threading.current_thread() is threading.main_thread()

    def interrupted(signum, _frame):
        nonlocal pending_signal
        if child is None:
            pending_signal = signum
            return
        raise SystemExit(128 + signum)

    if signals:
        previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        child = subprocess.Popen(
            command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, umask=0o077)
        if pending_signal is not None:
            raise SystemExit(128 + pending_signal)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                code = child.wait(timeout=min(heartbeat_interval, remaining) if heartbeat else remaining)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout) from None
                if heartbeat is not None:
                    heartbeat()
        if heartbeat is not None:
            heartbeat()
        completed = True
        return code
    finally:
        try:
            # 임대 갱신 오류·종료 신호도 시간 초과와 같은 경로로 자식 전체를 회수한다.
            if child is not None and not completed:
                if signals:
                    signal.signal(signal.SIGTERM, signal.SIG_IGN)
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        finally:
            if signals:
                signal.signal(signal.SIGTERM, previous)


def read_result(path, *, maximum=64 * 1024 * 1024):
    def invalid(*_):
        raise ValueError('WORKER_RESULT_INVALID')

    def fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                invalid()
            result[key] = value
        return result

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            invalid()
        return parsed

    try:
        fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                invalid()
            raw = stream.read(maximum + 1)
            if len(raw) > maximum:
                invalid()
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=fields,
                            parse_constant=invalid, parse_float=number)
        if not isinstance(result, dict):
            invalid()
        stack = [iter((result,))]
        while stack:
            try:
                value = next(stack[-1])
            except StopIteration:
                stack.pop()
                continue
            if isinstance(value, (dict, list)):
                if len(stack) > 128:
                    invalid()
                stack.append(iter(value.values() if isinstance(value, dict) else value))
        return result
    except (OSError, ValueError, RecursionError):
        raise ValueError('WORKER_RESULT_INVALID') from None
