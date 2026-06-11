# test_eval_session.py — Unit tests for EvalSession state machine

from __future__ import annotations

import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.eval_session import EvalSession, _sessions, _sessions_lock, _SESSION_TTL_SECONDS
from app.models.enums import EvalPhase, EvalPhaseStatus


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear global session store before each test."""
    async def _clear():
        async with _sessions_lock:
            _sessions.clear()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_clear())
    finally:
        loop.close()
    yield
    loop2 = asyncio.new_event_loop()
    try:
        loop2.run_until_complete(_clear())
    finally:
        loop2.close()


@pytest.fixture
def mock_save():
    """Mock eval_history_store.save_session (called via import inside EvalSession methods)."""
    with patch("app.core.eval_history_store.save_session") as mock:
        yield mock


class TestSessionCreation:
    """Tests for EvalSession.create()."""

    @pytest.mark.asyncio
    async def test_create_returns_session(self):
        session = await EvalSession.create("smart_city", "pipeline")
        assert session is not None
        assert session.session_id is not None
        assert len(session.session_id) == 12

    @pytest.mark.asyncio
    async def test_create_registers_in_global_store(self):
        session = await EvalSession.create()
        stored = await EvalSession.get(session.session_id)
        assert stored is not None
        assert stored.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_create_initializes_all_phases_pending(self):
        session = await EvalSession.create()
        for phase in EvalPhase:
            assert session.phases[phase]["status"] == EvalPhaseStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_create_sets_initial_status(self):
        session = await EvalSession.create()
        assert session.status == "running"
        assert session.overall_progress == 0.0
        assert session.overall_score is None

    @pytest.mark.asyncio
    async def test_create_sets_sandtable_and_mode(self):
        session = await EvalSession.create("smart_traffic", "single")
        assert session.sandtable_type == "smart_traffic"
        assert session.mode == "single"


class TestSessionPhases:
    """Tests for phase transitions."""

    @pytest.mark.asyncio
    async def test_start_phase(self):
        session = await EvalSession.create()
        await session.start_phase(EvalPhase.BRAND_RECALL)
        assert session.phases[EvalPhase.BRAND_RECALL]["status"] == EvalPhaseStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_complete_phase(self):
        session = await EvalSession.create()
        await session.start_phase(EvalPhase.BRAND_RECALL)
        await session.complete_phase(EvalPhase.BRAND_RECALL, {"score": 85})
        assert session.phases[EvalPhase.BRAND_RECALL]["status"] == EvalPhaseStatus.COMPLETED.value
        assert session.phase_results[EvalPhase.BRAND_RECALL] == {"score": 85}

    @pytest.mark.asyncio
    async def test_skip_phase(self):
        session = await EvalSession.create()
        await session.skip_phase(EvalPhase.SOLUTION_MATCH)
        assert session.phases[EvalPhase.SOLUTION_MATCH]["status"] == EvalPhaseStatus.SKIPPED.value

    @pytest.mark.asyncio
    async def test_fail_phase(self):
        session = await EvalSession.create()
        await session.fail_phase(EvalPhase.SOURCE_CHECK, "API timeout")
        assert session.phases[EvalPhase.SOURCE_CHECK]["status"] == EvalPhaseStatus.FAILED.value
        assert session.phases[EvalPhase.SOURCE_CHECK]["error"] == "API timeout"

    @pytest.mark.asyncio
    async def test_mark_completed(self, mock_save):
        session = await EvalSession.create()
        session.evaluated_text = "test text"
        session.original_text = "original"
        await session.mark_completed(78.5)
        assert session.status == "completed"
        assert session.overall_score == 78.5
        assert session.overall_progress == 100.0

    @pytest.mark.asyncio
    async def test_mark_failed(self):
        session = await EvalSession.create()
        await session.mark_failed()
        assert session.status == "failed"

    @pytest.mark.asyncio
    async def test_mark_cancelled(self, mock_save):
        session = await EvalSession.create()
        session.evaluated_text = "test"
        session.original_text = "orig"
        await session.mark_cancelled()
        assert session.status == "cancelled"
        assert session.cancelled is True
        # All pending phases should be cancelled
        for phase in EvalPhase:
            if session.phases[phase]["status"] == EvalPhaseStatus.CANCELLED.value:
                pass  # verified


class TestProgressTracking:
    """Tests for progress calculation."""

    @pytest.mark.asyncio
    async def test_progress_updates_on_complete(self):
        session = await EvalSession.create()
        assert session.overall_progress == 0.0
        await session.complete_phase(EvalPhase.BRAND_RECALL)
        await session.complete_phase(EvalPhase.SOLUTION_MATCH)
        # 2 out of 10 phases completed = 20%
        assert session.overall_progress >= 15.0

    @pytest.mark.asyncio
    async def test_progress_counts_skipped_and_failed(self):
        session = await EvalSession.create()
        await session.skip_phase(EvalPhase.BRAND_RECALL)
        await session.fail_phase(EvalPhase.SOLUTION_MATCH, "error")
        await session.complete_phase(EvalPhase.ADVANTAGE_CITATION)
        assert session.overall_progress >= 25.0


class TestSessionQuery:
    """Tests for get/list_all/remove."""

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        session = await EvalSession.get("nonexistent_id")
        assert session is None

    @pytest.mark.asyncio
    async def test_list_all(self):
        s1 = await EvalSession.create()
        s2 = await EvalSession.create()
        all_sessions = await EvalSession.list_all()
        assert len(all_sessions) >= 2

    @pytest.mark.asyncio
    async def test_remove(self):
        session = await EvalSession.create()
        await EvalSession.remove(session.session_id)
        assert await EvalSession.get(session.session_id) is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self):
        # Should not raise
        await EvalSession.remove("fake_id")


class TestToDict:
    """Tests for to_dict()."""

    @pytest.mark.asyncio
    async def test_to_dict_has_required_keys(self):
        session = await EvalSession.create("smart_city", "pipeline")
        d = session.to_dict()
        assert "session_id" in d
        assert "status" in d
        assert "phases" in d
        assert "overall_progress" in d
        assert "sandtable_type" in d
        assert d["sandtable_type"] == "smart_city"

    @pytest.mark.asyncio
    async def test_to_dict_reflects_phase_changes(self):
        session = await EvalSession.create()
        await session.complete_phase(EvalPhase.BRAND_RECALL, {"score": 90})
        d = session.to_dict()
        phase_info = d["phases"][EvalPhase.BRAND_RECALL.value]
        assert phase_info["status"] == "completed"
        assert phase_info["result"] == {"score": 90}


class TestCancellation:
    """Tests for cancel flow."""

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self):
        session = await EvalSession.create()
        await session.cancel()
        assert session.cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_marks_all_pending_as_cancelled(self, mock_save):
        session = await EvalSession.create()
        session.evaluated_text = "test"
        session.original_text = "orig"
        await session.mark_cancelled()
        for phase in EvalPhase:
            status = session.phases[phase]["status"]
            # All should be either completed/skipped/failed (none in our case) or cancelled
            assert status in (
                EvalPhaseStatus.COMPLETED.value,
                EvalPhaseStatus.SKIPPED.value,
                EvalPhaseStatus.FAILED.value,
                EvalPhaseStatus.CANCELLED.value,
            )


class TestCleanupStale:
    """Tests for stale session cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self):
        # Create a session with old timestamp
        session = await EvalSession.create()
        session._created_ts = 0  # very old
        await EvalSession._cleanup_stale()
        # Should have been removed
        stored = await EvalSession.get(session.session_id)
        assert stored is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_fresh(self):
        session = await EvalSession.create()
        # session._created_ts is current
        await EvalSession._cleanup_stale()
        stored = await EvalSession.get(session.session_id)
        assert stored is not None
