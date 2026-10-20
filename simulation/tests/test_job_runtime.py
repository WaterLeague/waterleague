"""실제 자식 프로세스의 중단·고아 방지와 손상된 결과 경계 검증."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from waterleague_sim import job_runtime


CHILD = """
import json, os, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1])
grandchild = subprocess.Popen([sys.executable, '-c',
    'import os,sys,time; from pathlib import Path; '
    'Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)',
    str(root/'grandchild')])
(root/'child').write_text(str(os.getpid()))
time.sleep(30)
"""


class JobRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.command = [sys.executable, '-c', CHILD, str(self.root)]
        self.environment = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL')}
        self.environment['PYTHONPATH'] = str(Path(job_runtime.__file__).resolve().parents[1])
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        for name in ('grandchild', 'child'):
            path = self.root/name
            if path.exists():
                try:
                    os.kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def assert_stopped(self):
        for name in ('child', 'grandchild'):
            self.assertTrue((self.root/name).is_file())
            pid = int((self.root/name).read_text())
            # 고아의 회수 시점은 OS에 맡기되 실행 중인 프로세스는 허용하지 않는다.
            limit = time.monotonic() + 3
            while True:
                status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                                        capture_output=True, text=True, check=False).stdout.strip()
                if not status or status.startswith('Z'):
                    break
                if time.monotonic() >= limit:
                    self.fail(f'{name} process still running')
                time.sleep(.02)

    def test_deadline_kills_native_process_and_its_descendant(self):
        before = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(subprocess.TimeoutExpired):
            job_runtime.run_process(self.command, env=self.environment, timeout=2)
        self.assert_stopped()
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_renewal_failure_reaps_processes_and_preserves_exception(self):
        failure = ConnectionError('TEST_DATABASE_UNAVAILABLE')
        def heartbeat():
            if (self.root/'grandchild').exists():
                raise failure
        with self.assertRaises(ConnectionError) as caught:
            job_runtime.run_process(self.command, env=self.environment, timeout=5,
                                    heartbeat=heartbeat, heartbeat_interval=.03)
        self.assertIs(caught.exception, failure)
        self.assert_stopped()

    def test_worker_sigterm_cleans_up_instead_of_leaving_native_process_running(self):
        wrapper = subprocess.Popen(
            [sys.executable, '-c',
             'import json,sys; from waterleague_sim.job_runtime import run_process; '
             'run_process(json.loads(sys.argv[1]),env={},timeout=30)',
             json.dumps(self.command)],
            env=self.environment, start_new_session=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not (self.root/'grandchild').exists():
                self.assertIsNone(wrapper.poll())
                if time.monotonic() >= deadline:
                    self.fail('native child did not start')
                time.sleep(.02)
            wrapper.send_signal(signal.SIGTERM)
            self.assertEqual(wrapper.wait(timeout=5), 128 + signal.SIGTERM)
            self.assert_stopped()
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
            wrapper.wait()

    def test_success_and_nonzero_exit_do_not_change_codes_or_signal_handler(self):
        before = signal.getsignal(signal.SIGTERM)
        for code in (0, 7):
            calls = []
            self.assertEqual(job_runtime.run_process(
                [sys.executable, '-c', f'raise SystemExit({code})'],
                env=self.environment, timeout=5, heartbeat=lambda: calls.append(1)), code)
            self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_shutdown_during_spawn_waits_for_handle_and_reaps_child(self):
        original = subprocess.Popen
        children = []
        def spawning(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child
        before = signal.getsignal(signal.SIGTERM)
        with patch.object(job_runtime.subprocess, 'Popen', side_effect=spawning):
            with self.assertRaises(SystemExit) as caught:
                job_runtime.run_process(self.command, env=self.environment, timeout=5)
        self.assertEqual(caught.exception.code, 128 + signal.SIGTERM)
        self.assertEqual(children[0].returncode, -signal.SIGKILL)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_expired_lease_does_not_start_an_engine(self):
        with patch.object(job_runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'LOST'):
                job_runtime.run_process(self.command, env=self.environment, timeout=5,
                    heartbeat=lambda: (_ for _ in ()).throw(ValueError('LEASE_LOST')))
            popen.assert_not_called()

    def test_result_reader_rejects_non_object_duplicate_nonfinite_and_deep_json(self):
        path = self.root/'result.json'
        path.write_text('{"volume":0.5,"label":"강우","nested":{"value":null}}')
        self.assertEqual(job_runtime.read_result(path)['volume'], .5)
        for raw in ('[]', 'null', '{"x":1,"x":2}', '{"x":{"v":1,"v":2}}',
                    '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":-1e999}',
                    '{"x":', '{"x":' + '[' * 2000 + '0' + ']' * 2000 + '}'):
            with self.subTest(raw=raw[:30]):
                path.write_text(raw)
                with self.assertRaisesRegex(ValueError, '^WORKER_RESULT_INVALID$'):
                    job_runtime.read_result(path)
        path.write_bytes(b'{"x":"\xff"}')
        with self.assertRaisesRegex(ValueError, '^WORKER_RESULT_INVALID$'):
            job_runtime.read_result(path)

    def test_result_reader_rejects_oversize_symlinks_and_special_files(self):
        path = self.root/'result.json'
        path.write_bytes(b'{"x":1}' + b' '*100)
        with self.assertRaisesRegex(ValueError, 'WORKER_RESULT_INVALID'):
            job_runtime.read_result(path, maximum=20)
        alias = self.root/'alias.json'
        alias.symlink_to(path)
        with self.assertRaisesRegex(ValueError, 'WORKER_RESULT_INVALID'):
            job_runtime.read_result(alias)
        fifo = self.root/'fifo'
        os.mkfifo(fifo)
        for invalid in (fifo, self.root, self.root/'missing'):
            with self.subTest(path=invalid.name), self.assertRaisesRegex(ValueError, 'WORKER_RESULT_INVALID'):
                job_runtime.read_result(invalid)


if __name__ == '__main__':
    unittest.main()
