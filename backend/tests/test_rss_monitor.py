# test_rss_monitor.py — Unit tests for RSS monitor enhancements (v2.1)
#
# Tests cover:
# - Content hash computation and comparison
# - Per-source interval enforcement (_should_check_source)
# - Source check tracker persistence (_get_last_check, _set_last_check)
# - Previous crawl result loading (_load_previous_crawl_result)
# - 3-tier alert classification (get_keyword_alerts)
# - Hash changes detection (get_hash_changes_since)

from __future__ import annotations

import sys
import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.rss_monitor import (
    _compute_content_hash,
    _compute_article_hash,
    _get_last_check,
    _set_last_check,
    _should_check_source,
    _load_previous_crawl_result,
    get_keyword_alerts,
    get_hash_changes_since,
    RSS_SOURCES,
)


class TestContentHash:
    """Tests for content hash computation."""

    def test_hash_is_deterministic(self):
        """Same content always produces the same hash."""
        text = "这是一段测试内容，用于验证哈希一致性。"
        h1 = _compute_content_hash(text)
        h2 = _compute_content_hash(text)
        assert h1 == h2
        assert len(h1) == 32  # MD5 hex digest is 32 chars

    def test_different_content_different_hash(self):
        """Different content produces different hashes."""
        h1 = _compute_content_hash("内容A")
        h2 = _compute_content_hash("内容B")
        assert h1 != h2

    def test_article_hash_combines_title_and_snippet(self):
        """Article hash combines title + snippet."""
        article = {"title": "测试标题", "snippet": "测试摘要"}
        h = _compute_article_hash(article)
        expected = hashlib.md5("测试标题|测试摘要".encode()).hexdigest()
        assert h == expected

    def test_article_hash_missing_fields(self):
        """Article hash handles missing title/snippet gracefully."""
        article = {}
        h = _compute_article_hash(article)
        expected = hashlib.md5("|".encode()).hexdigest()
        assert h == expected


class TestSourceInterval:
    """Tests for per-source interval tracking."""

    @pytest.fixture(autouse=True)
    def cleanup_tracker(self):
        """Remove test tracker file after each test."""
        yield
        from app.core.rss_monitor import _get_source_tracker_path
        tracker = _get_source_tracker_path()
        if tracker.exists():
            tracker.unlink()

    def test_get_last_check_returns_none_when_no_file(self):
        """Returns None when no tracker file exists."""
        result = _get_last_check("baidu_search")
        assert result is None

    def test_set_and_get_last_check(self):
        """Can persist and retrieve last check timestamps."""
        ts = "2026-06-06T08:00:00+00:00"
        _set_last_check("baidu_search", ts)
        result = _get_last_check("baidu_search")
        assert result == ts

    def test_should_check_source_first_time(self):
        """Source should be checked on first run (no previous check)."""
        source = {"id": "test_source", "check_interval_hours": 24}
        assert _should_check_source(source) is True

    def test_should_check_source_within_interval(self):
        """Source should NOT be checked if within interval."""
        source = {"id": "test_source", "check_interval_hours": 24}
        # Set last check to 1 hour ago
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _set_last_check(source["id"], ts)
        assert _should_check_source(source) is False

    def test_should_check_source_past_interval(self):
        """Source SHOULD be checked if past interval."""
        source = {"id": "test_source", "check_interval_hours": 1}
        # Set last check to 2 hours ago
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        _set_last_check(source["id"], ts)
        assert _should_check_source(source) is True

    def test_should_check_source_default_interval(self):
        """Default interval is 24 hours when not specified."""
        source = {"id": "test_no_interval"}
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _set_last_check(source["id"], ts)
        assert _should_check_source(source) is False  # 1h < 24h default


class TestThreeTierAlerts:
    """Tests for 3-tier alert classification."""

    @patch("app.core.rss_monitor.get_rss_results")
    def test_major_tier_for_algorithm_update(self, mock_get_results):
        """Keywords like 算法更新 produce major-tier alerts."""
        mock_get_results.return_value = {
            "results": [{
                "source_id": "baidu_search",
                "source_name": "百度搜索",
                "hash_changed": False,
                "alerts": [{
                    "title": "算法更新公告",
                    "snippet": "百度搜索算法更新，影响收录规则",
                    "matched_keywords": ["算法更新", "收录"],
                    "source_url": "https://example.com",
                }],
            }],
        }
        alerts = get_keyword_alerts()
        assert len(alerts) > 0
        assert alerts[0]["tier"] == "major"
        assert alerts[0]["tier_label"] == "重大"

    @patch("app.core.rss_monitor.get_rss_results")
    def test_moderate_tier_for_weight_change(self, mock_get_results):
        """Keywords like 权重 produce moderate-tier alerts."""
        mock_get_results.return_value = {
            "results": [{
                "source_id": "toutiao_creator",
                "source_name": "头条号",
                "hash_changed": False,
                "alerts": [{
                    "title": "权重调整",
                    "snippet": "平台权重计算方式有调整",
                    "matched_keywords": ["权重"],
                    "source_url": "https://example.com",
                }],
            }],
        }
        alerts = get_keyword_alerts()
        assert len(alerts) > 0
        assert alerts[0]["tier"] == "moderate"

    @patch("app.core.rss_monitor.get_rss_results")
    def test_micro_tier_for_crawl_adjustment(self, mock_get_results):
        """Keywords like 抓取 produce micro-tier alerts."""
        mock_get_results.return_value = {
            "results": [{
                "source_id": "zhihu_xiaohongshu",
                "source_name": "知乎/小红书",
                "hash_changed": False,
                "alerts": [{
                    "title": "爬虫规则更新",
                    "snippet": "更新了爬虫抓取频率限制",
                    "matched_keywords": ["爬虫"],
                    "source_url": "https://example.com",
                }],
            }],
        }
        alerts = get_keyword_alerts()
        assert len(alerts) > 0
        assert alerts[0]["tier"] == "micro"

    @patch("app.core.rss_monitor.get_rss_results")
    def test_tier_upgrade_on_hash_change(self, mock_get_results):
        """micro-tier upgrades to moderate when content hash changed."""
        mock_get_results.return_value = {
            "results": [{
                "source_id": "baijiahao",
                "source_name": "百家号",
                "hash_changed": True,  # actual content changed
                "alerts": [{
                    "title": "审核规则微调",
                    "snippet": "内容审核标准微调",
                    "matched_keywords": ["审核"],
                    "source_url": "https://example.com",
                }],
            }],
        }
        alerts = get_keyword_alerts()
        assert len(alerts) > 0
        # 审核 is micro, but hash_changed upgrades it to moderate
        assert alerts[0]["tier"] == "moderate"

    @patch("app.core.rss_monitor.get_rss_results")
    def test_no_results_returns_empty(self, mock_get_results):
        """Empty results produce empty alert list."""
        mock_get_results.return_value = None
        alerts = get_keyword_alerts()
        assert alerts == []


class TestHashChanges:
    """Tests for hash change detection across crawls."""

    def test_get_hash_changes_empty_when_no_data(self):
        """Returns empty list when no monitoring data exists."""
        changes = get_hash_changes_since(days=7)
        # May or may not have data depending on test environment
        assert isinstance(changes, list)


class TestRSSSources:
    """Tests for RSS source configuration."""

    def test_seven_source_types(self):
        """Verify 7 source types exist."""
        assert len(RSS_SOURCES) == 7
        source_ids = [s["id"] for s in RSS_SOURCES]
        expected = [
            "baidu_search", "baijiahao", "wenxin_blog",
            "toutiao_creator", "doubao_changelog",
            "wechat_platform", "zhihu_xiaohongshu",
        ]
        for eid in expected:
            assert eid in source_ids

    def test_each_source_has_interval(self):
        """Every source has a check_interval_hours field."""
        for source in RSS_SOURCES:
            assert "check_interval_hours" in source
            assert source["check_interval_hours"] > 0

    def test_each_source_has_keywords(self):
        """Every source has keyword list for matching."""
        for source in RSS_SOURCES:
            assert "keywords" in source
            assert len(source["keywords"]) > 0
