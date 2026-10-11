"""Nested hosted mutations must not wait on their own PostgreSQL lock."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading

import pytest
from app.video_studio import workspace_documents as documents


@pytest.fixture
def advisory_pool(monkeypatch):
    acquired, active = [], {}
    serial = 0

    @contextmanager
    def connection():
        nonlocal serial
        serial += 1
        identity = serial
        def execute(sql, params):
            key = params[0]
            assert key not in active, 'A second connection would deadlock on an outer lock'
            assert sql == 'SELECT pg_advisory_xact_lock(%s)'
            active[key] = identity
            acquired.append((identity, key))
        try:
            yield SimpleNamespace(execute=execute)
        finally:
            for key in [key for key, owner in active.items() if owner == identity]:
                active.pop(key)

    monkeypatch.setattr(documents, 'postgres_enabled', lambda: True)
    monkeypatch.setattr(documents, 'connection_pool', lambda: SimpleNamespace(connection=connection))
    return acquired, active


def test_same_resolved_path_reuses_outer_advisory_transaction(tmp_path, advisory_pool):
    acquired, active = advisory_pool
    with documents.document_lock(tmp_path / 'state.json'):
        with documents.document_lock(tmp_path / 'nested' / '..' / 'state.json'):
            assert len(acquired) == len(active) == 1
        assert len(active) == 1
    assert not active


def test_distinct_paths_keep_distinct_advisory_locks(tmp_path, advisory_pool):
    acquired, active = advisory_pool
    with documents.document_lock(tmp_path / 'parent.json'):
        with documents.document_lock(tmp_path / 'child.json'):
            assert len(active) == 2
    assert len(acquired) == 2 and not active


def test_failed_nested_mutation_releases_reentry_state(tmp_path, advisory_pool):
    acquired, active = advisory_pool
    with pytest.raises(ValueError, match='aborted'):
        with documents.document_lock(tmp_path / 'state.json'):
            with documents.document_lock(tmp_path / 'state.json'):
                raise ValueError('aborted')
    assert not active
    with documents.document_lock(tmp_path / 'state.json'):
        assert len(active) == 1
    assert len(acquired) == 2 and not active


def test_another_thread_still_serializes_on_the_same_path(tmp_path, advisory_pool):
    acquired, active = advisory_pool
    entered, waiting, release, second_entered = (threading.Event() for _ in range(4))
    def first():
        with documents.document_lock(tmp_path / 'state.json'):
            entered.set()
            assert release.wait(5)
    def second():
        assert entered.wait(5)
        waiting.set()
        with documents.document_lock(tmp_path / 'state.json'):
            second_entered.set()
    with ThreadPoolExecutor(max_workers=2) as executor:
        left, right = executor.submit(first), executor.submit(second)
        assert waiting.wait(5)
        assert not second_entered.wait(.1)
        release.set()
        left.result(timeout=5)
        right.result(timeout=5)
    assert second_entered.is_set() and len(acquired) == 2 and not active
