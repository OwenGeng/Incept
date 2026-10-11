"""Authenticated host bridge for the real Pi SDK subprocess, not an Agent loop."""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def run_process(config: dict, callback, check_cancel, progress=None, poll_controls=None) -> dict:
    root = Path(os.getenv('INCEPT_PROJECT_ROOT') or Path(__file__).resolve().parents[4])
    script = root / 'apps/video-vue/apps/agentRuntime/src/main.ts'
    node = shutil.which('node')
    if not node or not script.is_file():
        raise ValueError('Pi runtime is not installed; no fallback to the retired Agent. Install the video Agent runtime dependencies.')
    records = queue.Queue()
    with subprocess.Popen([node, '--experimental-strip-types', str(script)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        def reader(pipe, kind):
            while line := pipe.readline(64 * 1024 * 1024 + 1):
                records.put((kind, line))
            records.put((kind, None))
        for pipe, kind in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            threading.Thread(target=reader, args=(pipe, kind), daemon=True).start()
        def send(record):
            data = json.dumps(record, ensure_ascii=False).encode('utf-8') + b'\n'
            if len(data) > 64 * 1024 * 1024:
                raise ValueError('Pi context/media transport exceeds 64 MiB; narrow the selected media or create a new conversation.')
            with write_lock:
                process.stdin.write(data)
                process.stdin.flush()
        write_lock = threading.Lock()
        stopped = threading.Event()
        workers=ThreadPoolExecutor(max_workers=6,thread_name_prefix='linglonglab-pi-host')
        def respond(record):
            try:
                if len(inspect.signature(callback).parameters)>=3:
                    result=callback(record['kind'],record['payload'],lambda event:send({'id':record['id'],'event':event}))
                else: result=callback(record['kind'],record['payload'])
                check_cancel()
                send({'id':record['id'],'result':result})
            except Exception as error:
                message=str(error)[:1000]
                if config.get('apiKey'): message=message.replace(config['apiKey'],'[redacted]')
                try: send({'id':record['id'],'error':message})
                except (OSError,ValueError): pass  # The detached host already closed this attempt.
        def pump_controls():
            while not stopped.wait(.2):
                try:
                    if poll_controls:
                        for command in poll_controls():
                            send({'type':'control','command':command})
                except Exception:
                    # Main thread owns the public failure/cancellation channel.
                    stopped.set()
        try:
            send({'config': config})
            if poll_controls:
                threading.Thread(target=pump_controls,daemon=True).start()
            started = time.monotonic()
            diagnostics = ''
            while True:
                check_cancel()
                if time.monotonic() - started > 1800:
                    raise ValueError('Pi Agent run timed out; conversation retained for retry.')
                try:
                    kind, line = records.get(timeout=0.25)
                except queue.Empty:
                    continue
                if kind == 'stderr':
                    if line:
                        diagnostics = (diagnostics + line.decode('utf-8', errors='replace'))[-2000:]
                    continue
                if line is None:
                    raise ValueError('Pi runtime exited unexpectedly. Check the server runtime installation; conversation retained.')
                if len(line) > 64 * 1024 * 1024 or not line.endswith(b'\n'):
                    raise ValueError('Invalid or oversized Pi protocol record')
                record = json.loads(line)
                if record['type'] == 'request':
                    workers.submit(respond,record)
                elif record['type'] == 'event' and progress:
                    progress(record['event'])
                elif record['type']=='controlError' and progress:
                    progress({'type':'progress','content':'Active instruction could not be delivered; reopen the conversation and send it again.'})
                elif record['type'] == 'error':
                    check_cancel()
                    message = record.get('message', 'Pi runtime failed')[:1000]
                    if config.get('apiKey'):
                        message = message.replace(config['apiKey'], '[redacted]')
                    raise ValueError(message)
                elif record['type'] == 'result':
                    check_cancel()
                    return record
        finally:
            stopped.set()
            workers.shutdown(wait=False,cancel_futures=True)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
