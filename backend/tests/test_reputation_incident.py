"""舆情事件管理引擎单元测试"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.reputation_incident import (
    create_incident, get_incident, update_incident_status,
    list_incidents, get_incident_timeline,
    set_correction_content, mark_correction_published,
    get_reputation_stats, get_sentiment_trend,
)


class TestIncidentCRUD:
    """事件基本CRUD操作"""

    def test_create_incident(self, mock_config):
        incident = create_incident(
            platform="deepseek",
            query="武汉沙盘厂家推荐",
            ai_response="武汉微艺达是一家专业的沙盘定制公司。",
            sentiment={"polarity": "positive", "confidence": 80, "factual_accuracy": "accurate", "factual_issues": [], "summary": "正面提及"},
            brand_mentioned=True,
        )
        assert incident["incident_id"].startswith("inc_")
        assert incident["platform"] == "deepseek"
        assert incident["status"] == "open"
        assert incident["severity"] in ("low", "medium", "high", "critical")
        assert len(incident["timeline"]) == 1
        assert incident["timeline"][0]["action"] == "created"

    def test_create_incident_with_explicit_severity(self, mock_config):
        incident = create_incident(
            platform="doubao",
            query="微艺达好不好",
            ai_response="微艺达不靠谱，别选。",
            sentiment={"polarity": "negative", "factual_accuracy": "inaccurate", "confidence": 85},
            severity="critical",
        )
        assert incident["severity"] == "critical"

    def test_get_incident(self, mock_config):
        incident = create_incident(
            platform="wenxin",
            query="测试查询",
            ai_response="测试回复",
        )
        fetched = get_incident(incident["incident_id"])
        assert fetched is not None
        assert fetched["incident_id"] == incident["incident_id"]

    def test_get_nonexistent_incident(self, mock_config):
        fetched = get_incident("inc_nonexistent")
        assert fetched is None

    def test_persistence_across_calls(self, mock_config):
        """验证事件真的持久化到了JSON文件"""
        incident = create_incident(
            platform="kimi",
            query="持久化测试",
            ai_response="测试内容",
        )
        # 第二次读取应从文件加载
        fetched = get_incident(incident["incident_id"])
        assert fetched["platform"] == "kimi"
        assert fetched["query"] == "持久化测试"


class TestStatusTransitions:
    """状态流转测试"""

    def test_open_to_investigating(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        updated = update_incident_status(incident["incident_id"], "investigating", "开始调查")
        assert updated["status"] == "investigating"
        assert len(updated["timeline"]) == 2

    def test_investigating_to_responding(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        update_incident_status(incident["incident_id"], "investigating")
        updated = update_incident_status(incident["incident_id"], "responding")
        assert updated["status"] == "responding"

    def test_responding_to_resolved(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        update_incident_status(incident["incident_id"], "investigating")
        update_incident_status(incident["incident_id"], "responding")
        updated = update_incident_status(incident["incident_id"], "resolved", "问题已解决")
        assert updated["status"] == "resolved"
        assert updated["resolved_at"] is not None

    def test_dismiss_then_reopen(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        update_incident_status(incident["incident_id"], "dismissed", "不重要")
        fetched = get_incident(incident["incident_id"])
        assert fetched["status"] == "dismissed"
        # 重新打开
        updated = update_incident_status(incident["incident_id"], "open", "重新评估")
        assert updated["status"] == "open"

    def test_invalid_transition_raises(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        # open → resolved 不合法（必须经过中间状态）
        with pytest.raises(ValueError, match="状态流转不合法"):
            update_incident_status(incident["incident_id"], "resolved")

    def test_resolved_cannot_change(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        update_incident_status(incident["incident_id"], "investigating")
        update_incident_status(incident["incident_id"], "responding")
        update_incident_status(incident["incident_id"], "resolved")
        # resolved → investigating 不合法
        with pytest.raises(ValueError, match="状态流转不合法"):
            update_incident_status(incident["incident_id"], "investigating")


class TestListAndFilter:
    """列表和筛选测试"""

    def test_list_all(self, mock_config):
        create_incident(platform="deepseek", query="q1", ai_response="a1")
        create_incident(platform="doubao", query="q2", ai_response="a2")
        incidents = list_incidents()
        assert len(incidents) >= 2

    def test_filter_by_platform(self, mock_config):
        create_incident(platform="deepseek", query="q1", ai_response="a1")
        create_incident(platform="doubao", query="q2", ai_response="a2")
        filtered = list_incidents(platform="deepseek")
        assert all(i["platform"] == "deepseek" for i in filtered)

    def test_filter_by_severity(self, mock_config):
        create_incident(platform="deepseek", query="test", ai_response="test", severity="critical")
        create_incident(platform="doubao", query="test", ai_response="test", severity="low")
        filtered = list_incidents(severity="critical")
        assert all(i["severity"] == "critical" for i in filtered)

    def test_filter_by_status(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        # 正确状态流转: open → investigating → responding → resolved
        update_incident_status(incident["incident_id"], "investigating")
        update_incident_status(incident["incident_id"], "responding")
        update_incident_status(incident["incident_id"], "resolved")
        resolved = list_incidents(status="resolved")
        open_list = list_incidents(status="open")
        assert any(i["incident_id"] == incident["incident_id"] for i in resolved)
        # 该事件不应出现在open列表
        assert not any(i["incident_id"] == incident["incident_id"] for i in open_list)

    def test_limit_offset(self, mock_config):
        for i in range(10):
            create_incident(platform="deepseek", query=f"q{i}", ai_response=f"a{i}")
        results = list_incidents(limit=3, offset=2)
        assert len(results) <= 3


class TestCorrection:
    """纠正内容管理测试"""

    def test_set_correction_content(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        correction = "这是纠正内容：关于微艺达的不实信息需要进行澄清。"
        updated = set_correction_content(incident["incident_id"], correction)
        assert updated["correction_content"] == correction
        assert not updated["correction_published"]

    def test_mark_correction_published(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        set_correction_content(incident["incident_id"], "纠正内容")
        updated = mark_correction_published(incident["incident_id"])
        assert updated["correction_published"] is True

    def test_set_correction_nonexistent_incident(self, mock_config):
        with pytest.raises(ValueError, match="事件不存在"):
            set_correction_content("inc_nonexistent", "纠正内容")


class TestTimeline:
    """时间线测试"""

    def test_creation_timeline(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        timeline = get_incident_timeline(incident["incident_id"])
        assert len(timeline) == 1
        assert timeline[0]["action"] == "created"
        assert timeline[0]["status"] == "open"

    def test_timeline_accumulates(self, mock_config):
        incident = create_incident(platform="deepseek", query="test", ai_response="test")
        update_incident_status(incident["incident_id"], "investigating", "第一次备注")
        update_incident_status(incident["incident_id"], "responding", "第二次备注")
        timeline = get_incident_timeline(incident["incident_id"])
        assert len(timeline) == 3
        assert timeline[1]["action"] == "started_investigation"
        assert timeline[2]["action"] == "started_response"

    def test_nonexistent_incident_timeline(self, mock_config):
        timeline = get_incident_timeline("inc_nonexistent")
        assert timeline == []


class TestStats:
    """统计测试"""

    def test_empty_stats(self, mock_config):
        stats = get_reputation_stats()
        assert "total_incidents" in stats
        assert "positive_rate" in stats
        assert "negative_rate" in stats

    def test_stats_with_incidents(self, mock_config):
        create_incident(
            platform="deepseek", query="test1", ai_response="正面评价",
            sentiment={"polarity": "positive", "confidence": 80, "factual_accuracy": "accurate", "factual_issues": [], "summary": "test"},
            severity="low",
        )
        create_incident(
            platform="doubao", query="test2", ai_response="负面评价",
            sentiment={"polarity": "negative", "confidence": 70, "factual_accuracy": "inaccurate", "factual_issues": [], "summary": "test"},
            severity="critical",
        )
        stats = get_reputation_stats()
        assert stats["total_incidents"] >= 2
        assert stats["open_incidents"] >= 2
        assert stats["critical_incidents"] >= 1

    def test_sentiment_trend(self, mock_config):
        trend = get_sentiment_trend(days=30)
        assert isinstance(trend, list)
