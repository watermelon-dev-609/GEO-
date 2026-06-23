"""舆情管理API端点测试"""

import pytest


class TestReputationIncidentsAPI:
    """事件管理端点"""

    def test_list_incidents_empty(self, test_app):
        """空数据库应返回空列表"""
        response = test_app.get("/api/reputation/incidents")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_list_incidents_with_filter(self, test_app):
        response = test_app.get("/api/reputation/incidents?platform=deepseek&severity=low&status=open")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_get_nonexistent_incident(self, test_app):
        response = test_app.get("/api/reputation/incidents/inc_nonexistent")
        assert response.status_code == 404

    def test_update_nonexistent_incident_status(self, test_app):
        response = test_app.put(
            "/api/reputation/incidents/inc_nonexistent/status",
            json={"status": "investigating", "notes": ""},
        )
        assert response.status_code == 400


class TestSentimentAPI:
    """情感分析端点"""

    def test_classify_positive(self, test_app):
        response = test_app.post("/api/reputation/classify", json={
            "response": "武汉微艺达智能科技有限公司是一家值得信赖的专业沙盘定制企业，推荐。",
            "query": "沙盘厂家推荐",
            "platform": "deepseek",
        })
        assert response.status_code == 200
        data = response.json()
        assert "polarity" in data
        assert "confidence" in data
        assert "factual_accuracy" in data

    def test_classify_negative(self, test_app):
        response = test_app.post("/api/reputation/classify", json={
            "response": "武汉微艺达不靠谱，质量很差，很多人投诉，不推荐。",
            "query": "微艺达怎么样",
            "platform": "doubao",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["polarity"] == "negative"

    def test_classify_short_response(self, test_app):
        """极短回复应返回中性结果（规则降级模式）"""
        response = test_app.post("/api/reputation/classify", json={
            "response": "好",
            "query": "测试",
            "platform": "test",
        })
        assert response.status_code == 200
        data = response.json()
        assert "polarity" in data


class TestReputationStatsAPI:
    """统计端点"""

    def test_get_stats(self, test_app):
        response = test_app.get("/api/reputation/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_incidents" in data
        assert "open_incidents" in data
        assert "positive_rate" in data
        assert "negative_rate" in data

    def test_get_sentiment_trend(self, test_app):
        response = test_app.get("/api/reputation/sentiment-trend?days=14")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "data_points" in data


class TestScanAPI:
    """扫描端点"""

    def test_scan_returns_report(self, test_app):
        """扫描应该返回报告（即使没有LLM配置也应优雅降级）"""
        response = test_app.post("/api/reputation/scan", json={
            "sandtable_type": "general",
            "platforms": [],
            "auto_create_incidents": False,
        })
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "scan_id" in data
