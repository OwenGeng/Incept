"""Owned loopback native host shared by concurrent runs in one API worker.

The random IPC secret never enters Agent configs, journals or public responses.
Failure is closed: attempts are never replayed through a retired runtime.
"""
from __future__ import annotations

import atexit
import http.client
import inspect
import json
import os
import queue
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class _Endpoint:
    port: int
    generation: str
    pid: int
    secret: str = field(repr=False)


def _encoded(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('Native host transport exceeds 64 MiB; narrow the selected media or context.')
    return data


def _post(endpoint, path, value, *, timeout=10):
    connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=timeout)
    try:
        connection.request('POST', path, body=_encoded(value), headers={
            'content-type': 'application/json', 'x-linglonglab-native-host': endpoint.secret})
        response = connection.getresponse()
        data = response.read(64 * 1024 + 1)
        if len(data) > 64 * 1024:
            raise ValueError('Invalid native host acknowledgement')
        if response.status not in {200, 202}:
            message = json.loads(data).get('error', 'Native host rejected the private operation')
            raise ValueError(str(message).replace(endpoint.secret, '[redacted]')[:1000])
        return json.loads(data)
    finally:
        connection.close()


class NativeHostManager:
    """Lazily supervised process. Runs never set global model credentials/cwd."""
    def __init__(self, *, command=None, max_parents=5, run_timeout=1800):
        if not isinstance(max_parents, int) or not 1 <= max_parents <= 20:
            raise ValueError('Invalid native host parent budget')
        self._command, self._max_parents, self._run_timeout = command, max_parents, run_timeout
        self._lock = threading.RLock()
        self._process = self._endpoint = None
        self._closed = False
        self._owner_pid = os.getpid()
        self._callbacks = ThreadPoolExecutor(max_workers=30, thread_name_prefix='linglonglab-native-callback')
        self._callback_slots = threading.BoundedSemaphore(94)
        self._callback_lock = threading.RLock()
        self._callback_owners = {}

    def _submit_callback(self, owner, callback):
        with self._callback_lock:
            if self._closed:
                raise ValueError('Native host manager is shutting down')
            state=self._callback_owners.setdefault(owner,{'scheduled':0,'pending':deque()})
            if len(state['pending']) >= 16:
                raise ValueError('Native callback budget exhausted for this user; wait for cancelled requests to close.')
            if not self._callback_slots.acquire(blocking=False):
                if not state['scheduled'] and not state['pending']: self._callback_owners.pop(owner,None)
                raise ValueError('Native callback capacity exhausted; wait for pending requests to close.')
            future=Future()
            task={'owner':owner,'future':future,'callback':callback,'queued':True,'finished':False}
            state['pending'].append(task)
            def cancelled(done):
                if done.cancelled():
                    with self._callback_lock:
                        if task['queued']: self._finish_callback(task)
            future.add_done_callback(cancelled)
            self._schedule_callbacks(owner)
            return future

    def _schedule_callbacks(self, owner):
        # Waiting tasks occupy bounded receipts, never worker threads. Six
        # stalled callbacks from one account cannot consume all thirty workers.
        state=self._callback_owners.get(owner)
        while not self._closed and state and state['scheduled']<6 and state['pending']:
            task=state['pending'].popleft()
            task['queued']=False
            state['scheduled']+=1
            def run(task=task):
                try:
                    if task['future'].set_running_or_notify_cancel():
                        try: task['future'].set_result(task['callback']())
                        except BaseException as error: task['future'].set_exception(error)
                finally:
                    self._finish_callback(task)
            try:
                worker=self._callbacks.submit(run)
                worker.add_done_callback(lambda done,task=task:self._finish_callback(task) if done.cancelled() else None)
            except BaseException as error:
                task['future'].set_exception(error)
                self._finish_callback(task)

    def _finish_callback(self,task):
        with self._callback_lock:
            if task['finished']: return
            task['finished']=True
            state=self._callback_owners[task['owner']]
            if task['queued']:
                state['pending'].remove(task)
            else:
                state['scheduled']-=1
                if not task['future'].done(): task['future'].cancel()
            self._callback_slots.release()
            self._schedule_callbacks(task['owner'])
            if not state['scheduled'] and not state['pending']:
                self._callback_owners.pop(task['owner'],None)

    def identity(self):
        with self._lock:
            process = self._process
            live = process is not None and process.poll() is None
            return {'pid': process.pid if live else None,
                    'generation': self._endpoint.generation if live and self._endpoint else None}

    def _start(self):
        with self._lock:
            if self._closed or self._owner_pid != os.getpid():
                raise ValueError('Native host manager is unavailable in this worker')
            if self._process is not None and self._process.poll() is None:
                return self._endpoint
            if self._process is not None:
                self._dispose(self._process)
            root = Path(os.getenv('INCEPT_PROJECT_ROOT') or Path(__file__).resolve().parents[4])
            script = root / 'apps/video-vue/apps/agentRuntime/src/hostServer.ts'
            node = shutil.which('node')
            if self._command is None and (not node or not script.is_file()):
                raise ValueError('Native Toonflow host is not installed; no retired Agent fallback is available.')
            command = self._command or [node, '--experimental-strip-types', str(script)]
            secret, generation = secrets.token_hex(32), uuid.uuid4().hex
            environment = {**os.environ, 'LINGLONGLAB_NATIVE_HOST_TOKEN': secret,
                           'LINGLONGLAB_NATIVE_HOST_GENERATION': generation,
                           'LINGLONGLAB_NATIVE_HOST_MAX_PARENTS': str(self._max_parents)}
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=environment, close_fds=True)
            ready = queue.Queue(maxsize=1)
            def stdout_reader():
                try:
                    while line := process.stdout.readline(8193):
                        if len(line) > 8192 or not line.endswith(b'\n'):
                            continue
                        try:
                            record = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if isinstance(record, dict) and record.get('type') == 'ready':
                            try:
                                ready.put_nowait(record)
                            except queue.Full:
                                pass
                except (OSError, ValueError):
                    # Shutdown can close a pipe while its drain thread exits.
                    return
            def stderr_reader():
                # Drain without exposing provider payloads/credentials that a
                # dependency might include in its diagnostics.
                try:
                    while process.stderr.read(8192):
                        pass
                except (OSError, ValueError):
                    return
            threading.Thread(target=stdout_reader, daemon=True, name='native-host-ready').start()
            threading.Thread(target=stderr_reader, daemon=True, name='native-host-diagnostics').start()
            deadline = time.monotonic() + 15
            try:
                while True:
                    if process.poll() is not None:
                        raise ValueError('Native Toonflow host failed to start; inspect its installed runtime dependencies.')
                    if time.monotonic() >= deadline:
                        raise ValueError('Native Toonflow host readiness timed out')
                    try:
                        record = ready.get(timeout=.1)
                        break
                    except queue.Empty:
                        continue
                port = record.get('port')
                if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535 or record.get('generation') != generation:
                    raise ValueError('Invalid private native host readiness response')
                endpoint = _Endpoint(port, generation, process.pid, secret)
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request('GET', '/ready', headers={'x-linglonglab-native-host': secret})
                    response = connection.getresponse()
                    state = json.loads(response.read(8193))
                    if response.status != 200 or state.get('generation') != generation:
                        raise ValueError('Native host readiness authentication failed')
                finally:
                    connection.close()
                self._process, self._endpoint = process, endpoint
                return endpoint
            except BaseException:
                self._dispose(process)
                raise

    @staticmethod
    def _dispose(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for pipe in (process.stdout, process.stderr):
            if pipe:
                pipe.close()

    def shutdown(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            with self._callback_lock:
                waiting=[task['future'] for state in self._callback_owners.values() for task in state['pending']]
            for future in waiting: future.cancel()
            self._callbacks.shutdown(wait=False, cancel_futures=True)
            process, endpoint = self._process, self._endpoint
            self._process = self._endpoint = None
            if process is None:
                return
            if process.poll() is None and endpoint:
                try:
                    _post(endpoint, '/shutdown', {}, timeout=2)
                    process.wait(timeout=3)
                except (OSError, ValueError, subprocess.TimeoutExpired, http.client.HTTPException):
                    pass
            self._dispose(process)

    def run(self, config, callback, check_cancel, progress=None, poll_controls=None):
        check_cancel()
        endpoint = self._start()
        run_id = uuid.uuid4().hex
        stopped = threading.Event()
        records = queue.Queue(maxsize=32)
        failures, failed = [], threading.Event()
        budget_lock = threading.Lock()
        queued_bytes = 0
        connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=10)
        response = raw_socket = None
        owner = config.get('callbackScope') or config.get('cwd') or 'private-daemon-test'
        futures, futures_lock = set(), threading.Lock()
        def send(value, action='reply'):
            if stopped.is_set():
                raise ValueError('Native SDK attempt has already ended')
            return _post(endpoint, f'/run/{run_id}/{action}', value)
        def redact(error):
            message = str(error).replace(endpoint.secret, '[redacted]')
            if isinstance(config.get('apiKey'), str) and config['apiKey']:
                message = message.replace(config['apiKey'], '[redacted]')
            return message[:1000]
        def fail(error):
            if not failed.is_set():
                failures.append(error)
                failed.set()
        def reader():
            nonlocal queued_bytes
            try:
                while not stopped.is_set():
                    line = response.readline(MAX_BYTES + 1)
                    if not line:
                        raise ValueError('Native Toonflow host disconnected; this attempt was not replayed.')
                    if len(line) > MAX_BYTES or not line.endswith(b'\n'):
                        raise ValueError('Invalid or oversized native host record')
                    record = json.loads(line)
                    if not isinstance(record, dict) or not isinstance(record.get('type'), str):
                        raise ValueError('Invalid native host protocol record')
                    with budget_lock:
                        if queued_bytes + len(line) > MAX_BYTES:
                            raise ValueError('Native host event reader budget exhausted')
                        queued_bytes += len(line)
                    records.put((record, len(line)), timeout=1)
                    if record['type'] in {'result', 'error'}:
                        return
            except Exception as error:
                if not stopped.is_set():
                    fail(error)
        def respond(record):
            try:
                check_cancel()
                if len(inspect.signature(callback).parameters) >= 3:
                    result = callback(record['kind'], record['payload'], lambda event: send({'id': record['id'], 'event': event}))
                else:
                    result = callback(record['kind'], record['payload'])
                check_cancel()
                send({'id': record['id'], 'result': result})
            except Exception as error:
                try:
                    send({'id': record['id'], 'error': redact(error)})
                except (OSError, ValueError, http.client.HTTPException):
                    pass
        def pump_controls():
            while not stopped.wait(.2):
                try:
                    if poll_controls:
                        for command in poll_controls():
                            send({'command': command}, 'control')
                except Exception as error:
                    fail(error)
                    return
        try:
            connection.request('POST', '/run', body=_encoded({'runId': run_id, 'config': config}), headers={
                'content-type': 'application/json', 'x-linglonglab-native-host': endpoint.secret})
            raw_socket = connection.sock
            response = connection.getresponse()
            if response.status != 200:
                detail = response.read(8193)
                message = json.loads(detail).get('error', 'Native host refused this attempt')
                raise ValueError(redact(message))
            if response.getheader('x-native-host-generation') != endpoint.generation or response.getheader('content-type') != 'application/x-ndjson':
                raise ValueError('Native host run readiness identity does not match')
            if raw_socket:
                raw_socket.settimeout(None)
            threading.Thread(target=reader, daemon=True, name='native-host-events').start()
            if poll_controls:
                threading.Thread(target=pump_controls, daemon=True, name='native-host-controls').start()
            started = time.monotonic()
            total_callbacks = 0
            while True:
                check_cancel()
                if failed.is_set():
                    raise ValueError(redact(failures[0]))
                if time.monotonic() - started > self._run_timeout:
                    raise ValueError('Native Toonflow attempt timed out; conversation retained for retry.')
                try:
                    record, size = records.get(timeout=.2)
                except queue.Empty:
                    continue
                with budget_lock:
                    queued_bytes -= size
                if record['type'] == 'request':
                    if not isinstance(record.get('id'), str) or not record['id'].startswith(run_id + ':') or not isinstance(record.get('kind'), str) or 'payload' not in record:
                        raise ValueError('Native callback identity is invalid')
                    total_callbacks += 1
                    if total_callbacks > 100_000:
                        raise ValueError('Native callback total budget exhausted')
                    future=self._submit_callback(owner,lambda record=record:respond(record))
                    with futures_lock: futures.add(future)
                    def forget(done):
                        with futures_lock: futures.discard(done)
                    future.add_done_callback(forget)
                elif record['type'] == 'event' and progress:
                    progress(record['event'])
                elif record['type'] == 'controlError' and progress:
                    progress({'type': 'progress', 'content': 'Active instruction could not be delivered; reopen the conversation and send it again.'})
                elif record['type'] == 'error':
                    check_cancel()
                    raise ValueError(redact(record.get('message', 'Native Toonflow host failed')))
                elif record['type'] == 'result':
                    check_cancel()
                    return record
        except (OSError, http.client.HTTPException) as error:
            check_cancel()
            raise ValueError('Native Toonflow host became unavailable; this attempt was not replayed.') from error
        finally:
            # Abort this UUID only; never terminate a shared host for one user.
            try:
                _post(endpoint, f'/run/{run_id}/abort', {}, timeout=2)
            except (OSError, ValueError, http.client.HTTPException):
                pass
            stopped.set()
            with futures_lock:
                pending_futures=list(futures)
            for future in pending_futures: future.cancel()
            if raw_socket:
                try:
                    raw_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if response:
                response.close()
            connection.close()


_manager_lock = threading.Lock()
_manager = None


def _host():
    global _manager
    with _manager_lock:
        if _manager is None or _manager._owner_pid != os.getpid():
            _manager = NativeHostManager()
        return _manager


def run_native(config, callback, check_cancel, progress=None, poll_controls=None):
    return _host().run(config, callback, check_cancel, progress, poll_controls)


def host_identity():
    """Read-only process identity: no URL, key, config or context is exposed."""
    with _manager_lock:
        return _manager.identity() if _manager else {'pid': None, 'generation': None}


def shutdown_host():
    global _manager
    with _manager_lock:
        manager, _manager = _manager, None
    if manager:
        manager.shutdown()


atexit.register(shutdown_host)
