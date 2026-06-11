"""审计日志中间件 — 拦截所有API请求并记录操作轨迹
使用纯ASGI中间件避免BaseHTTPMiddleware破坏SSE流式响应"""

from __future__ import annotations
import json
import time
import logging
from pathlib import Path

from starlette.types import ASGIApp, Scope, Receive, Send

from app.utils.config import load_settings

logger = logging.getLogger(__name__)


class AuditLogMiddleware:
    """纯ASGI中间件 — 记录所有API请求（不影响SSE流）"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = (time.perf_counter() - start) * 1000
            try:
                self._record(
                    method=scope.get("method", ""),
                    path=scope.get("path", ""),
                    client_ip=scope.get("client", ("unknown", 0))[0],
                    status=status_code,
                    duration_ms=round(duration, 2),
                )
            except Exception as e:
                logger.warning(f"审计日志记录失败: {e}")

    @staticmethod
    def _record(method: str, path: str, client_ip: str, status: int, duration_ms: float):
        today = time.strftime("%Y-%m-%d")
        settings = load_settings()
        data_dir = settings.get("system", {}).get("data_dir", "./data")
        base = Path(data_dir)
        if not base.is_absolute():
            base = Path(__file__).resolve().parent.parent.parent / data_dir
        audit_dir = base / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": method,
            "path": path,
            "client_ip": client_ip,
            "status": status,
            "duration_ms": duration_ms,
        }

        filepath = audit_dir / f"{today}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
