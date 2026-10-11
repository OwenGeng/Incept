"""Exercise the actual daemon/HTTP transport without calling a model provider."""
import http.client
import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.video_studio import native_host


class Cancelled(RuntimeError):
    pass


@pytest.fixture
def daemon(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'video-vue/apps/agentRuntime/src/hostServer.ts'
    assert source.is_file()
    script = tmp_path / 'fake-native-host.mjs'
    script.write_text('''
import { createNativeHost } from SOURCE;
const runner = async (config, bridge, send, controls) => {
  const deltas = [];
  controls.register(command => send({type:'control', user:config.user, command}));
  send({type:'started', user:config.user, pid:process.pid});
  const value = await bridge('fake', {user:config.user}, controls.signal, event => {
    deltas.push(event.delta); send({type:'delta', user:config.user, delta:event.delta});
  });
  if (config.error) throw Error(config.apiKey + ':intentional failure');
  return {text:config.user + ':' + value.text, pid:process.pid, deltas};
};
const host = await createNativeHost({runner, secret:process.env.LINGLONGLAB_NATIVE_HOST_TOKEN,
  generation:process.env.LINGLONGLAB_NATIVE_HOST_GENERATION,
  maxParents:Number(process.env.LINGLONGLAB_NATIVE_HOST_MAX_PARENTS)});
process.stdout.write(JSON.stringify({type:'ready',port:host.port,generation:host.generation})+'\\n');
process.once('SIGTERM',()=>{void host.shutdown()});
'''.replace('SOURCE', json.dumps(source.as_uri())))
    manager = native_host.NativeHostManager(command=[shutil.which('node'), '--experimental-strip-types', str(script)], run_timeout=10)
    yield manager
    manager.shutdown()


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.01)
    raise AssertionError('Timed out waiting for a native host test boundary')


def open_run(endpoint, user):
    run_id = uuid.uuid4().hex
    connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=5)
    connection.request('POST', '/run', body=json.dumps({'runId': run_id, 'config': {'user': user}}),
        headers={'content-type': 'application/json', 'x-linglonglab-native-host': endpoint.secret})
    response = connection.getresponse()
    assert response.status == 200
    first = json.loads(response.readline())
    second = json.loads(response.readline())
    assert first['type'] == 'event' and second['type'] == 'request'
    return run_id, connection, response, second


def test_five_runs_share_one_host_and_one_cancel_leaves_other_four(daemon):
    barrier = threading.Barrier(5)
    release = threading.Event()
    cancellation = threading.Event()
    events = {str(index): [] for index in range(5)}
    def callback(kind, payload, delta):
        assert kind == 'fake'
        barrier.wait(timeout=5)
        delta({'type': 'text_delta', 'delta': payload['user']})
        assert release.wait(timeout=5)
        return {'text': payload['user']}
    def run(user):
        def check():
            if user == '0' and cancellation.is_set():
                raise Cancelled('Only user 0 was cancelled')
        return daemon.run({'user': user}, callback, check, events[user].append)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {str(index): pool.submit(run, str(index)) for index in range(5)}
        wait_for(lambda: all(any(event['type'] == 'delta' for event in values) for values in events.values()))
        pid = daemon.identity()['pid']
        assert pid and all(next(event for event in values if event['type'] == 'started')['pid'] == pid for values in events.values())
        cancellation.set()
        with pytest.raises(Cancelled, match='Only user 0'):
            futures['0'].result(timeout=5)
        assert daemon.identity()['pid'] == pid
        release.set()
        for user in ('1', '2', '3', '4'):
            result = futures[user].result(timeout=5)
            assert result['text'] == f'{user}:{user}' and result['pid'] == pid and result['deltas'] == [user]
        assert all(all(event.get('user') == user for event in values) for user, values in events.items())


def test_admission_limits_sixth_parent_without_affecting_five_active(daemon):
    endpoint = daemon._start()
    streams = [open_run(endpoint, str(index)) for index in range(5)]
    try:
        with pytest.raises(ValueError, match='5 active parent run limit'):
            daemon.run({'user': 'sixth'}, lambda *args: pytest.fail('Sixth run must not call a provider'), lambda: None)
        assert daemon.identity()['pid'] == endpoint.pid
        for run_id, _, response, record in streams:
            native_host._post(endpoint, f'/run/{run_id}/reply', {'id': record['id'], 'result': {'text': run_id}})
            assert json.loads(response.readline())['type'] == 'result'
    finally:
        for _, connection, response, _ in streams:
            response.close()
            connection.close()


def test_callback_ids_bind_to_run_and_reject_late_or_wrong_run_replies(daemon):
    endpoint = daemon._start()
    left, left_connection, left_response, left_record = open_run(endpoint, 'left')
    right, right_connection, right_response, right_record = open_run(endpoint, 'right')
    try:
        with pytest.raises(ValueError, match='belongs to another run'):
            native_host._post(endpoint, f'/run/{right}/reply', {'id': left_record['id'], 'result': {'text': 'wrong'}})
        native_host._post(endpoint, f'/run/{left}/reply', {'id': left_record['id'], 'result': {'text': 'left-only'}})
        assert json.loads(left_response.readline())['text'] == 'left:left-only'
        with pytest.raises(ValueError, match='no longer active'):
            native_host._post(endpoint, f'/run/{left}/reply', {'id': left_record['id'], 'result': {'text': 'late'}})
        native_host._post(endpoint, f'/run/{right}/reply', {'id': right_record['id'], 'result': {'text': 'right-only'}})
        assert json.loads(right_response.readline())['text'] == 'right:right-only'
    finally:
        left_response.close(); left_connection.close()
        right_response.close(); right_connection.close()


def test_private_secret_required_and_not_present_in_public_identity_or_errors(daemon):
    endpoint = daemon._start()
    connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=5)
    try:
        connection.request('GET', '/ready')
        response = connection.getresponse()
        assert response.status == 401
        assert endpoint.secret not in response.read().decode()
    finally:
        connection.close()
    assert set(daemon.identity()) == {'pid', 'generation'}
    assert endpoint.secret not in repr(endpoint)
    with pytest.raises(ValueError) as error:
        daemon.run({'user': 'owner', 'error': True, 'apiKey': 'provider-private-key'}, lambda *args: {'text': 'done'}, lambda: None)
    assert 'provider-private-key' not in str(error.value) and endpoint.secret not in str(error.value)


def test_control_commands_and_streaming_callback_deltas_stay_in_owned_run(daemon):
    events, controls = [], [{'type': 'steer', 'prompt': 'Continue this task', 'controlId': 'owned-control'}]
    release = threading.Event()
    def callback(kind, payload, delta):
        delta({'type': 'text_delta', 'delta': 'streamed text'})
        assert release.wait(timeout=5)
        return {'text': 'controlled'}
    def poll():
        current = controls[:]
        controls.clear()
        return current
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(daemon.run, {'user': 'owner'}, callback, lambda: None, events.append, poll)
        wait_for(lambda: any(event['type'] == 'control' for event in events))
        release.set()
        result = future.result(timeout=5)
    assert result['deltas'] == ['streamed text']
    assert next(event for event in events if event['type'] == 'control')['command']['controlId'] == 'owned-control'


def test_proven_host_exit_fails_current_attempt_and_new_attempt_uses_new_generation(daemon):
    reached, release = threading.Event(), threading.Event()
    def callback(*args):
        reached.set()
        release.wait(timeout=5)
        return {'text': 'old'}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(daemon.run, {'user': 'old'}, callback, lambda: None)
        assert reached.wait(timeout=5)
        before = daemon.identity()
        daemon._process.kill()
        daemon._process.wait(timeout=3)
        with pytest.raises(ValueError, match='disconnected|unavailable'):
            future.result(timeout=5)
        release.set()
    result = daemon.run({'user': 'new'}, lambda *args: {'text': 'new'}, lambda: None)
    after = daemon.identity()
    assert result['text'] == 'new:new'
    assert before['pid'] != after['pid'] and before['generation'] != after['generation']


def test_client_disconnect_aborts_only_its_run(daemon):
    endpoint = daemon._start()
    abandoned, abandoned_connection, abandoned_response, _ = open_run(endpoint, 'abandoned')
    # HTTPResponse.close closes this owned response socket, causing the daemon
    # to abort the run's signal and reject only its pending callbacks.
    abandoned_response.close()
    abandoned_connection.close()
    wait_for(lambda: _active_count(endpoint) == 0)
    assert daemon.run({'user': 'healthy'}, lambda *args: {'text': 'healthy'}, lambda: None)['text'] == 'healthy:healthy'
    with pytest.raises(ValueError, match='no longer active'):
        native_host._post(endpoint, f'/run/{abandoned}/abort', {})


def _active_count(endpoint):
    connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=3)
    try:
        connection.request('GET', '/ready', headers={'x-linglonglab-native-host': endpoint.secret})
        return json.loads(connection.getresponse().read())['activeParents']
    finally:
        connection.close()


def test_python_shutdown_disposes_owned_host_and_prevents_manager_reuse(daemon):
    daemon.run({'user': 'owner'}, lambda *args: {'text': 'done'}, lambda: None)
    process = daemon._process
    daemon.shutdown()
    assert process.poll() is not None and daemon.identity() == {'pid': None, 'generation': None}
    with pytest.raises(ValueError, match='unavailable'):
        daemon.run({'user': 'new'}, lambda *args: {'text': 'new'}, lambda: None)


def test_repeated_cancelled_stalled_callbacks_are_bounded_and_other_owner_runs(daemon):
    release=threading.Event()
    started=[]
    started_lock=threading.Lock()
    def stalled(*args):
        with started_lock: started.append(threading.current_thread().name)
        release.wait(10)
        return {'text':'late'}
    try:
        for index in range(20):
            cancel=threading.Event()
            def check():
                if cancel.is_set(): raise Cancelled('owned cancelled')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(daemon.run, {'user':'stalled','callbackScope':'same-owner'}, stalled, check)
                if index<6: wait_for(lambda:len(started)==index+1)
                else: wait_for(lambda:any(state['pending'] for state in daemon._callback_owners.values()))
                cancel.set()
                with pytest.raises(Cancelled): future.result(timeout=5)
        assert len(started)==6 and len(set(started))==6
        assert len(daemon._callbacks._threads)<=6
        result=daemon.run({'user':'healthy','callbackScope':'other-owner'},lambda *args:{'text':'healthy'},lambda:None)
        assert result['text']=='healthy:healthy'
        assert len(daemon._callbacks._threads)<=7
    finally:
        release.set()
        wait_for(lambda:not daemon._callback_owners)


def test_manager_callback_budget_has_thirty_workers_and_at_most_sixty_four_queued(daemon):
    release=threading.Event()
    started=[]
    lock=threading.Lock()
    def blocked():
        with lock: started.append(True)
        release.wait(10)
    futures=[]
    try:
        for index in range(94):
            futures.append(daemon._submit_callback('owner-'+str(index%16),blocked))
        wait_for(lambda:len(started)==30)
        assert len(daemon._callbacks._threads)==30
        assert len(futures)-len(started)==64
        with pytest.raises(ValueError,match='capacity exhausted'):
            daemon._submit_callback('extra-owner',blocked)
        for future in futures: future.cancel()
        assert len(started)==30
    finally:
        release.set()
        wait_for(lambda:not daemon._callback_owners)
