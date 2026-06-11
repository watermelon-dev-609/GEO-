"""流量数据连接器 — GA4 + 百度统计 API 拉取与本地快照存储

设计原则：
- 每个数据源一个独立Connector类（参考SEODataImporter模式）
- 统一输出 TrafficDailySnapshot 格式，按日存储JSON
- 支持通过API Key/Token认证，凭据存储在 data/traffic/config.json
- 拉取失败不阻断系统运行，返回空快照+错误信息
"""

from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.utils.config import get_data_dir

logger = logging.getLogger(__name__)


def _get_traffic_dir() -> Path:
    d = get_data_dir() / "traffic"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_config() -> dict[str, Any]:
    """加载流量源配置"""
    config_file = _get_traffic_dir() / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"sources": {}}


def save_config(config: dict[str, Any]) -> None:
    """保存流量源配置（原子写入）"""
    import tempfile
    config_file = _get_traffic_dir() / "config.json"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=_get_traffic_dir()
    ) as tmp:
        json.dump(config, tmp, ensure_ascii=False, indent=2)
    Path(tmp.name).replace(config_file)


def load_traffic_snapshots(days: int = 30, source: str = "") -> list[dict[str, Any]]:
    """加载指定天数内的流量快照

    Args:
        days: 回溯天数
        source: 数据源过滤（ga4/baidu_tongji），空则全部

    Returns:
        按日期升序排列的快照列表
    """
    traffic_dir = _get_traffic_dir()
    cutoff = datetime.now() - timedelta(days=days)
    snapshots = []

    for f in sorted(traffic_dir.glob("*.json")):
        if f.name == "config.json":
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                continue
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if source and data.get("source", "") != source:
                continue
            snapshots.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return snapshots


def get_traffic_summary(days: int = 30) -> dict[str, Any]:
    """聚合流量汇总（供API和报表使用）

    Returns:
        {
            period_start, period_end,
            total_page_views, total_visitors, total_sessions,
            avg_bounce_rate_pct, ai_referral_visits,
            daily_snapshots[], by_source{}
        }
    """
    snapshots = load_traffic_snapshots(days=days)
    if not snapshots:
        now = datetime.now().strftime("%Y-%m-%d")
        past = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return {
            "period_start": past, "period_end": now,
            "total_page_views": 0, "total_visitors": 0,
            "total_sessions": 0, "avg_bounce_rate_pct": 0.0,
            "ai_referral_visits": 0,
            "daily_snapshots": [], "by_source": {},
        }

    total_pv = sum(s.get("page_views", 0) for s in snapshots)
    total_uv = sum(s.get("unique_visitors", 0) for s in snapshots)
    total_sessions = sum(s.get("sessions", 0) for s in snapshots)
    total_ai = sum(s.get("ai_referral_visits", 0) for s in snapshots)
    avg_bounce = (
        sum(s.get("bounce_rate_pct", 0) for s in snapshots) / len(snapshots)
        if snapshots else 0.0
    )

    by_source: dict[str, dict[str, int]] = {}
    for s in snapshots:
        src = s.get("source", "unknown")
        if src not in by_source:
            by_source[src] = {"page_views": 0, "visitors": 0, "sessions": 0}
        by_source[src]["page_views"] += s.get("page_views", 0)
        by_source[src]["visitors"] += s.get("unique_visitors", 0)
        by_source[src]["sessions"] += s.get("sessions", 0)

    return {
        "period_start": snapshots[0].get("date", "") if snapshots else "",
        "period_end": snapshots[-1].get("date", "") if snapshots else "",
        "total_page_views": total_pv,
        "total_visitors": total_uv,
        "total_sessions": total_sessions,
        "avg_bounce_rate_pct": round(avg_bounce, 1),
        "ai_referral_visits": total_ai,
        "daily_snapshots": snapshots,
        "by_source": by_source,
    }


# ══════════════════════════════════════════════════════════════
# GA4 Connector
# ══════════════════════════════════════════════════════════════

class GA4Connector:
    """Google Analytics 4 Data API 连接器

    使用服务账号JSON密钥认证，调用 runReport 获取基础指标。
    如需使用，需在Google Cloud Console启用 Analytics Data API，
    并将服务账号添加为GA4媒体资源的"查看者"。
    """

    API_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"

    def __init__(self, property_id: str = "", credentials_json: str = ""):
        self.property_id = property_id
        self.credentials_json = credentials_json
        self._access_token: str = ""
        self._token_expiry: float = 0

    async def _get_access_token(self) -> str:
        """获取OAuth 2.0 access token（服务账号）"""
        import base64
        from datetime import datetime as dt

        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        try:
            creds = json.loads(self.credentials_json) if isinstance(self.credentials_json, str) else self.credentials_json
        except (json.JSONDecodeError, TypeError):
            logger.warning("GA4: 无法解析服务账号凭据JSON")
            return ""

        # 构建JWT assertion
        import hashlib
        import hmac

        header = {"alg": "RS256", "typ": "JWT"}
        now = int(time.time())
        payload = {
            "iss": creds.get("client_email", ""),
            "scope": "https://www.googleapis.com/auth/analytics.readonly",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        # 简化：使用httpx直接请求（实际生产环境建议用 google-auth 库）
        # 此处使用服务账号密钥的私钥签名JWT
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key = serialization.load_pem_private_key(
                creds.get("private_key", "").encode(), password=None
            )
            header_b64 = _b64url(json.dumps(header).encode())
            payload_b64 = _b64url(json.dumps(payload).encode())
            signature_input = f"{header_b64}.{payload_b64}".encode()
            signature = private_key.sign(signature_input, padding.PKCS1v15(), hashes.SHA256())
            assertion = f"{header_b64}.{payload_b64}.{_b64url(signature)}"

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
                if resp.status_code == 200:
                    token_data = resp.json()
                    self._access_token = token_data.get("access_token", "")
                    self._token_expiry = time.time() + token_data.get("expires_in", 3600)
                    return self._access_token
                else:
                    logger.warning(f"GA4 OAuth失败: {resp.status_code} {resp.text[:200]}")
        except ImportError:
            logger.warning("GA4: cryptography库未安装，无法签名JWT。请 pip install cryptography")
        except Exception as e:
            logger.warning(f"GA4 JWT签名失败: {e}")

        return ""

    async def fetch_daily_report(self, date: str = "") -> dict[str, Any]:
        """拉取指定日期的GA4报告

        Args:
            date: 日期 YYYY-MM-DD，默认为昨天

        Returns:
            {date, source, page_views, unique_visitors, sessions,
             bounce_rate_pct, avg_session_duration_sec,
             top_landing_pages[], top_referrers[], ai_referral_visits, error?}
        """
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        token = await self._get_access_token()
        if not token:
            return {
                "date": date, "source": "ga4",
                "page_views": 0, "unique_visitors": 0, "sessions": 0,
                "bounce_rate_pct": 0.0, "avg_session_duration_sec": 0.0,
                "top_landing_pages": [], "top_referrers": [],
                "ai_referral_visits": 0,
                "error": "GA4认证失败：请检查服务账号凭据和API权限",
            }

        url = self.API_URL.format(property_id=self.property_id)

        # 请求体：基础指标 + UTM-AI过滤
        request_body = {
            "dateRanges": [{"startDate": date, "endDate": date}],
            "metrics": [
                {"name": "screenPageViews"},
                {"name": "totalUsers"},
                {"name": "sessions"},
                {"name": "bounceRate"},
                {"name": "averageSessionDuration"},
            ],
            "dimensions": [
                {"name": "landingPage"},
                {"name": "sessionSource"},
            ],
            "orderBys": [
                {"metric": {"metricName": "screenPageViews"}, "desc": True},
            ],
            "limit": 50,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=request_body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    error_msg = f"GA4 API错误 {resp.status_code}: {resp.text[:200]}"
                    logger.warning(error_msg)
                    return {
                        "date": date, "source": "ga4",
                        "page_views": 0, "unique_visitors": 0, "sessions": 0,
                        "bounce_rate_pct": 0.0, "avg_session_duration_sec": 0.0,
                        "top_landing_pages": [], "top_referrers": [],
                        "ai_referral_visits": 0,
                        "error": error_msg,
                    }

                data = resp.json()
                rows = data.get("rows", [])

                total_pv = 0
                total_users = 0
                total_sessions = 0
                total_bounce = 0.0
                total_duration = 0.0
                row_count = 0
                landing_pages: list[dict] = []
                referrers: dict[str, int] = {}
                ai_visits = 0

                for row in rows:
                    dims = row.get("dimensionValues", [])
                    metrics = row.get("metricValues", [])
                    if len(dims) >= 2 and len(metrics) >= 5:
                        page = dims[0].get("value", "")
                        source_val = dims[1].get("value", "")
                        pv = int(metrics[0].get("value", "0"))
                        users = int(metrics[1].get("value", "0"))
                        sessions_val = int(metrics[2].get("value", "0"))
                        bounce = float(metrics[3].get("value", "0"))
                        duration = float(metrics[4].get("value", "0"))

                        total_pv += pv
                        total_users += users
                        total_sessions += sessions_val
                        total_bounce += bounce
                        total_duration += duration
                        row_count += 1

                        landing_pages.append({"url": page, "views": pv, "users": users})
                        referrers[source_val] = referrers.get(source_val, 0) + pv

                        # UTM AI引用检测
                        if "ai_referral" in source_val.lower() or "utm_medium=ai_referral" in page:
                            ai_visits += pv

                # 平均值计算
                avg_bounce = (total_bounce / row_count) if row_count > 0 else 0.0
                avg_duration = (total_duration / row_count) if row_count > 0 else 0.0

                snapshot = {
                    "date": date,
                    "source": "ga4",
                    "page_views": total_pv,
                    "unique_visitors": total_users,
                    "sessions": total_sessions,
                    "bounce_rate_pct": round(avg_bounce, 1),
                    "avg_session_duration_sec": round(avg_duration, 1),
                    "top_landing_pages": sorted(landing_pages, key=lambda x: x["views"], reverse=True)[:10],
                    "top_referrers": [
                        {"source": k, "views": v}
                        for k, v in sorted(referrers.items(), key=lambda x: x[1], reverse=True)[:10]
                    ],
                    "ai_referral_visits": ai_visits,
                }

                # 持久化存储
                _save_snapshot(snapshot)
                return snapshot

        except httpx.RequestError as e:
            logger.warning(f"GA4网络请求失败: {e}")
            return {
                "date": date, "source": "ga4",
                "page_views": 0, "unique_visitors": 0, "sessions": 0,
                "bounce_rate_pct": 0.0, "avg_session_duration_sec": 0.0,
                "top_landing_pages": [], "top_referrers": [],
                "ai_referral_visits": 0,
                "error": f"网络请求失败: {e}",
            }


# ══════════════════════════════════════════════════════════════
# 百度统计 Connector
# ══════════════════════════════════════════════════════════════

class BaiduTongjiConnector:
    """百度统计 API 连接器

    使用百度统计开放API（https://api.baidu.com/json/tongji/v1/ReportService/getData），
    通过用户名+密码+token方式认证获取站点报告数据。
    需要先在百度统计开放平台注册应用获取api_key和secret_key。
    """

    API_URL = "https://api.baidu.com/json/tongji/v1/ReportService/getData"
    AUTH_URL = "https://api.baidu.com/oauth/2.0/token"

    def __init__(self, site_id: str = "", username: str = "",
                 password: str = "", api_key: str = "", secret_key: str = ""):
        self.site_id = site_id
        self.username = username
        self.password = password
        self.api_key = api_key
        self.secret_key = secret_key
        self._access_token: str = ""
        self._token_expiry: float = 0

    async def _get_access_token(self) -> str:
        """获取百度OAuth 2.0 access token"""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.AUTH_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.api_key,
                        "client_secret": self.secret_key,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token", "")
                    self._token_expiry = time.time() + data.get("expires_in", 2592000)
                    return self._access_token
                else:
                    logger.warning(f"百度统计OAuth失败: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"百度统计认证请求失败: {e}")

        return ""

    async def fetch_daily_report(self, date: str = "") -> dict[str, Any]:
        """拉取指定日期的百度统计报告

        Args:
            date: 日期 YYYY-MM-DD，默认为昨天

        Returns:
            标准化的快照dict（与GA4格式一致）
        """
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        token = await self._get_access_token()
        if not token:
            return self._make_empty_snapshot(date, "baidu_tongji",
                "百度统计认证失败：请检查api_key/secret_key")

        # 百度统计API请求参数
        body = {
            "header": {
                "username": self.username,
                "password": self.password,
                "token": token,
                "account_type": 1,
            },
            "body": {
                "site_id": self.site_id,
                "method": "overview/getTimeTrendRpt",
                "start_date": date.replace("-", ""),
                "end_date": date.replace("-", ""),
                "metrics": "pv_count,visitor_count,visit_count,bounce_ratio,avg_visit_time",
                "source": "all",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.API_URL,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    error_msg = f"百度统计API错误 {resp.status_code}: {resp.text[:200]}"
                    logger.warning(error_msg)
                    return self._make_empty_snapshot(date, "baidu_tongji", error_msg)

                result = resp.json()
                error_code = result.get("header", {}).get("failures", [{}])[0].get("code", 0) if isinstance(result.get("header"), dict) else result.get("error_code", 0)

                if error_code != 0:
                    error_msg = f"百度统计返回错误: {result.get('header', {}).get('failures', [{}])[0].get('reason', str(result))}"
                    logger.warning(error_msg)
                    return self._make_empty_snapshot(date, "baidu_tongji", error_msg)

                # 解析百度统计数据
                data_rows = result.get("body", {}).get("data", [{}])[0].get("result", {}).get("items", [])
                if not data_rows:
                    return self._make_empty_snapshot(date, "baidu_tongji")

                # items格式: [[pv_count, visitor_count, visit_count, bounce_ratio, avg_visit_time], ...]
                row = data_rows[0] if isinstance(data_rows[0], list) else list(data_rows[0].values())
                pv = int(row[0]) if len(row) > 0 else 0
                visitors = int(row[1]) if len(row) > 1 else 0
                visits = int(row[2]) if len(row) > 2 else 0
                bounce = float(row[3]) if len(row) > 3 else 0.0
                duration = float(row[4]) if len(row) > 4 else 0.0

                snapshot = {
                    "date": date,
                    "source": "baidu_tongji",
                    "page_views": pv,
                    "unique_visitors": visitors,
                    "sessions": visits,
                    "bounce_rate_pct": round(bounce, 1),
                    "avg_session_duration_sec": round(duration, 1),
                    "top_landing_pages": [],  # 百度简版API不返回此数据
                    "top_referrers": [],
                    "ai_referral_visits": 0,  # 需通过百度高级API单独查询
                }

                _save_snapshot(snapshot)
                return snapshot

        except httpx.RequestError as e:
            logger.warning(f"百度统计网络请求失败: {e}")
            return self._make_empty_snapshot(date, "baidu_tongji", f"网络请求失败: {e}")

    def _make_empty_snapshot(self, date: str, source: str, error: str = "") -> dict[str, Any]:
        return {
            "date": date, "source": source,
            "page_views": 0, "unique_visitors": 0, "sessions": 0,
            "bounce_rate_pct": 0.0, "avg_session_duration_sec": 0.0,
            "top_landing_pages": [], "top_referrers": [],
            "ai_referral_visits": 0,
            "error": error,
        }


# ══════════════════════════════════════════════════════════════
# 统一拉取入口
# ══════════════════════════════════════════════════════════════

def _save_snapshot(snapshot: dict[str, Any]) -> None:
    """保存单日快照到JSON文件（按源+日期命名）"""
    import tempfile
    source = snapshot.get("source", "unknown")
    date_str = snapshot.get("date", datetime.now().strftime("%Y-%m-%d"))
    filename = f"{source}_{date_str}.json"
    filepath = _get_traffic_dir() / filename
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=_get_traffic_dir()
    ) as tmp:
        json.dump(snapshot, tmp, ensure_ascii=False, indent=2)
    Path(tmp.name).replace(filepath)


async def fetch_and_store_traffic(source: str, date: str = "") -> dict[str, Any]:
    """统一入口：拉取指定源的流量数据并存储

    Args:
        source: "ga4" 或 "baidu_tongji"
        date: 日期 YYYY-MM-DD

    Returns:
        标准化快照dict
    """
    config = _get_config()
    source_cfg = config.get("sources", {}).get(source, {})

    if source == "ga4":
        connector = GA4Connector(
            property_id=source_cfg.get("property_id", ""),
            credentials_json=source_cfg.get("credentials_json", ""),
        )
        return await connector.fetch_daily_report(date)
    elif source == "baidu_tongji":
        connector = BaiduTongjiConnector(
            site_id=source_cfg.get("site_id", ""),
            api_key=source_cfg.get("api_key", ""),
            secret_key=source_cfg.get("secret_key", ""),
            username=source_cfg.get("username", ""),
            password=source_cfg.get("password", ""),
        )
        return await connector.fetch_daily_report(date)
    else:
        return {"date": date or datetime.now().strftime("%Y-%m-%d"), "source": source,
                "page_views": 0, "error": f"不支持的数据源: {source}"}
