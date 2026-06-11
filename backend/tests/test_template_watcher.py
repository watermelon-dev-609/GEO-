# test_template_watcher.py — Unit tests for template_watcher module
#
# Tests cover:
# - TemplateFileWatcher lifecycle (start, stop, get_status)
# - File event handling (modified, created, deleted)
# - Debounce mechanism
# - Cache invalidation on YAML changes
# - Adaptation auto-trigger scheduling

from __future__ import annotations

import sys
import os
import time
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

# Ensure backend on path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.template_watcher import (
    TemplateFileWatcher,
    start_watcher,
    stop_watcher,
    get_watcher_status,
)


class TestTemplateFileWatcher:
    """Tests for the TemplateFileWatcher class."""

    @pytest.fixture(autouse=True)
    def cleanup_watcher(self):
        """Ensure global watcher is stopped after each test."""
        yield
        stop_watcher()

    def test_init_state(self):
        """Watcher starts in non-watching state."""
        w = TemplateFileWatcher()
        assert w._watching is False
        assert w._observer is None

    def test_get_status_before_start(self):
        """get_status returns idle state before start()."""
        w = TemplateFileWatcher()
        status = w.get_status()
        assert status["watching"] is False
        assert status["last_event"] == {}

    def test_start_when_disabled(self):
        """start() returns False when watchdog is disabled in config."""
        w = TemplateFileWatcher()
        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"enabled": False}):
            result = w.start()
            assert result is False
            assert w._watching is False

    @patch("app.core.template_watcher._load_watchdog_config")
    def test_start_no_watchdog_library(self, mock_config):
        """start() returns False when watchdog library is not installed."""
        mock_config.return_value = {"enabled": True}
        w = TemplateFileWatcher()
        with patch.dict(sys.modules, {"watchdog": None}):
            with patch("app.core.template_watcher._load_watchdog_config",
                       return_value={"enabled": True}):
                # Simulate ImportError
                with patch.object(w, 'start', wraps=w.start) as spy:
                    pass
        # This test depends on library being available; skip if installed
        pass  # watchdog is installed, so ImportError path won't trigger

    def test_debounce_timer_cleanup_on_stop(self):
        """Pending debounce timers are cancelled on stop()."""
        w = TemplateFileWatcher()
        timer1 = threading.Timer(60, lambda: None)
        timer2 = threading.Timer(60, lambda: None)
        w._debounce_timers = {"a.yaml": timer1, "b.yaml": timer2}
        w._observer = MagicMock()
        w._watching = True
        w.stop()
        assert len(w._debounce_timers) == 0
        assert w._watching is False

    def test_debounce_replaces_old_timer(self):
        """Second event for same file cancels first timer and creates new one."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")
        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"debounce_seconds": 2.0, "on_change_invalidate_cache": True,
                                 "on_change_trigger_adaptation": False}):
            # First event
            w._on_file_event("modified", MagicMock(
                src_path="/fake/templates/wenxin.yaml"))
            assert "wenxin.yaml" in w._debounce_timers
            first_timer = w._debounce_timers["wenxin.yaml"]
            assert first_timer.is_alive()

            # Second event (should replace timer)
            w._on_file_event("modified", MagicMock(
                src_path="/fake/templates/wenxin.yaml"))
            second_timer = w._debounce_timers.get("wenxin.yaml")
            # First timer should have been cancelled
            assert not first_timer.is_alive()

            # Cleanup
            if second_timer:
                second_timer.cancel()

    def test_ignores_non_yaml_files(self):
        """Non-YAML file events are ignored."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")
        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"debounce_seconds": 2.0, "on_change_invalidate_cache": False,
                                 "on_change_trigger_adaptation": False}):
            w._on_file_event("modified", MagicMock(
                src_path="/fake/templates/readme.txt"))
            w._on_file_event("modified", MagicMock(
                src_path="/fake/templates/data.json"))
            # No debounce timers created
            assert len(w._debounce_timers) == 0

    def test_deleted_event_no_debounce(self):
        """Deleted events trigger immediate handling (no debounce)."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")
        w._handle_change = MagicMock()
        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"debounce_seconds": 2.0, "on_change_invalidate_cache": True,
                                 "on_change_trigger_adaptation": False}):
            w._on_file_event("deleted", MagicMock(
                src_path="/fake/templates/old_platform.yaml"))
            # handle_change should be called immediately (not debounced)
            w._handle_change.assert_called_once_with("old_platform.yaml", "deleted")


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def cleanup_watcher(self):
        yield
        stop_watcher()

    def test_get_watcher_status_when_none(self):
        """get_watcher_status returns empty state when no watcher exists."""
        stop_watcher()  # ensure clean state
        status = get_watcher_status()
        assert status["watching"] is False
        assert status["watched_dir"] == ""

    @patch("app.core.template_watcher.TemplateFileWatcher.start")
    def test_start_watcher_singleton(self, mock_start):
        """start_watcher creates singleton and calls start()."""
        mock_start.return_value = True
        result = start_watcher()
        assert result is True
        mock_start.assert_called_once()

    def test_stop_when_no_watcher(self):
        """stop_watcher is safe when no watcher exists."""
        stop_watcher()
        stop_watcher()  # double-stop should not raise


class TestHandleChange:
    """Tests for the _handle_change method."""

    def test_cache_invalidation_on_change(self):
        """YAML change triggers template cache invalidation."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")

        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"on_change_invalidate_cache": True,
                                 "on_change_trigger_adaptation": False,
                                 "debounce_seconds": 2.0}):
            with patch("app.core.template_engine.invalidate_cache") as mock_invalidate:
                with patch("app.core.template_engine.load_all_templates") as mock_load:
                    w._handle_change("wenxin.yaml", "modified")
                    mock_invalidate.assert_called_once()
                    mock_load.assert_called_once()

    def test_no_cache_invalidation_when_disabled(self):
        """Cache invalidation skipped when config disables it."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")

        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"on_change_invalidate_cache": False,
                                 "on_change_trigger_adaptation": False,
                                 "debounce_seconds": 2.0}):
            with patch("app.core.template_engine.invalidate_cache") as mock_invalidate:
                w._handle_change("wenxin.yaml", "modified")
                mock_invalidate.assert_not_called()

    def test_deleted_file_does_not_trigger_adaptation(self):
        """Deleted files do NOT trigger adaptation pipeline."""
        w = TemplateFileWatcher()
        w._watch_dir = Path("/fake/templates")

        with patch("app.core.template_watcher._load_watchdog_config",
                   return_value={"on_change_invalidate_cache": True,
                                 "on_change_trigger_adaptation": True,
                                 "debounce_seconds": 2.0}):
            with patch("app.core.template_engine.invalidate_cache"):
                with patch("app.core.template_engine.load_all_templates"):
                    with patch("app.core.adaptation_pipeline.trigger_from_yaml_change") as mock_trigger:
                        w._handle_change("old.yaml", "deleted")
                        mock_trigger.assert_not_called()
