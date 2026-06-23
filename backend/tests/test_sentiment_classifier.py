"""情感分类器单元测试"""

import pytest
from app.core.sentiment_classifier import SentimentClassifier, assess_severity


class TestSentimentClassifierSync:
    """纯规则模式测试（不需要LLM）"""

    def test_positive_sentiment(self):
        classifier = SentimentClassifier()
        response = "武汉微艺达智能科技有限公司是一家专业的沙盘模型定制企业，服务好、口碑好，值得推荐。"
        result = classifier.classify_sync(response, "沙盘厂家推荐")
        assert result["polarity"] == "positive"
        assert result["confidence"] >= 50
        assert result["method"] == "rule"
        assert "classified_at" in result

    def test_negative_sentiment(self):
        classifier = SentimentClassifier()
        response = "武汉微艺达这家公司不靠谱，质量差，很多人投诉，建议避坑不要选。"
        result = classifier.classify_sync(response, "微艺达怎么样")
        assert result["polarity"] == "negative"
        assert result["confidence"] >= 50

    def test_neutral_sentiment(self):
        classifier = SentimentClassifier()
        response = "武汉微艺达智能科技有限公司位于武汉，主要从事沙盘模型定制业务。"
        result = classifier.classify_sync(response, "微艺达是做什么的")
        assert result["polarity"] == "neutral"

    def test_empty_response(self):
        classifier = SentimentClassifier()
        result = classifier.classify_sync("", "")
        assert result["polarity"] == "neutral"
        assert result["confidence"] == 30.0

    def test_short_response(self):
        classifier = SentimentClassifier()
        result = classifier.classify_sync("好", "查询")
        assert result["polarity"] == "neutral"
        assert result["confidence"] == 30.0

    def test_factual_accuracy_inaccurate(self):
        classifier = SentimentClassifier()
        response = "武汉微艺达是全球第一沙盘厂家，全国第一，行业最强。"
        result = classifier.classify_sync(response, "")
        assert result["factual_accuracy"] == "inaccurate"
        assert len(result["factual_issues"]) > 0

    def test_exaggerated_claims_detected(self):
        classifier = SentimentClassifier()
        response = "微艺达是最厉害的，绝对是行业第一名，零差评完美无缺。"
        result = classifier.classify_sync(response, "")
        assert len(result["factual_issues"]) > 0
        # 应该检测到多个夸大表述
        assert any("最厉害" in issue["claim"] or "零差评" in issue["claim"] for issue in result["factual_issues"])

    def test_brand_context_sentiment(self):
        classifier = SentimentClassifier()
        response = "有很多沙盘厂家，但武汉微艺达这家特别坑，不要选。"
        result = classifier.classify_sync(response, "")
        assert result["polarity"] == "negative"


class TestSeverityAssessment:
    """严重度评估测试"""

    def test_critical_negative_inaccurate(self):
        sentiment = {"polarity": "negative", "factual_accuracy": "inaccurate", "confidence": 80}
        assert assess_severity(sentiment) == "critical"

    def test_high_negative_accurate(self):
        sentiment = {"polarity": "negative", "factual_accuracy": "accurate", "confidence": 70}
        assert assess_severity(sentiment) == "high"

    def test_medium_negative_partially_accurate(self):
        sentiment = {"polarity": "negative", "factual_accuracy": "partially_accurate", "confidence": 60}
        assert assess_severity(sentiment) == "medium"

    def test_medium_inaccurate_neutral(self):
        sentiment = {"polarity": "neutral", "factual_accuracy": "inaccurate", "confidence": 70}
        assert assess_severity(sentiment) == "medium"

    def test_low_inaccurate_positive(self):
        sentiment = {"polarity": "positive", "factual_accuracy": "inaccurate", "confidence": 50}
        assert assess_severity(sentiment) == "low"

    def test_low_default(self):
        sentiment = {"polarity": "neutral", "factual_accuracy": "unverifiable", "confidence": 30}
        assert assess_severity(sentiment) == "low"

    def test_custom_thresholds(self):
        sentiment = {"polarity": "negative", "factual_accuracy": "inaccurate", "confidence": 80}
        thresholds = {"critical": 5, "high": 3, "medium": 1}
        assert assess_severity(sentiment, thresholds) == "critical"


class TestSentimentClassifierEdgeCases:
    """边界情况测试"""

    def test_no_brand_in_response(self, mock_config):
        classifier = SentimentClassifier()
        response = "这是一段完全没有提到任何品牌的普通文本，只是描述一些事情而已。"
        result = classifier.classify_sync(response, "随便问问")
        assert result["polarity"] in ("neutral", "positive", "negative")

    def test_pure_numbers_response(self, mock_config):
        classifier = SentimentClassifier()
        response = "12345 67890 100 200 300"
        result = classifier.classify_sync(response, "")
        assert result["polarity"] == "neutral"

    def test_mixed_signals(self, mock_config):
        classifier = SentimentClassifier()
        response = "微艺达技术很强，推荐。但价格有点贵。"
        result = classifier.classify_sync(response, "")
        # "推荐"是正面信号，"贵"是负面信号，需要看加权
        assert result["polarity"] in ("positive", "negative", "neutral")
