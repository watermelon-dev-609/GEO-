"""评测会话状态机 — 管理阶段流转、取消、中间结果"""

from __future__ import annotations
import uuid
import time
import asyncio
import logging
from datetime import datetime, timezone
from app.models.enums import EvalPhase, EvalPhaseStatus

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 7200  # 2小时过期

_sessions: dict[str, "EvalSession"] = {}
_sessions_lock = asyncio.Lock()


def _now_ts() -> float:
    return time.time()


class EvalSession:
    """一次完整的评测会话"""

    def __init__(self, sandtable_type: str = "", mode: str = "pipeline"):
        self.__init_args__(sandtable_type, mode)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        self._cancelled = True
        logger.info(f"Session {self.session_id}: cancel requested")

    def start_phase(self, phase: EvalPhase):
        self.phases[phase]["status"] = EvalPhaseStatus.RUNNING.value
        self._update_progress()

    def complete_phase(self, phase: EvalPhase, result: dict | None = None):
        self.phases[phase]["status"] = EvalPhaseStatus.COMPLETED.value
        if result is not None:
            self.phase_results[phase] = result
        self._update_progress()

    def skip_phase(self, phase: EvalPhase):
        self.phases[phase]["status"] = EvalPhaseStatus.SKIPPED.value
        self._update_progress()

    def fail_phase(self, phase: EvalPhase, error: str):
        self.phases[phase]["status"] = EvalPhaseStatus.FAILED.value
        self.phases[phase]["error"] = error
        self._update_progress()

    def mark_completed(self, overall_score: float):
        self.status = "completed"
        self.overall_score = overall_score
        self.overall_progress = 100.0
        self._save_to_disk()

    def _save_to_disk(self):
        """持久化到磁盘"""
        try:
            from app.core.eval_history_store import save_session
            save_session(self, self.evaluated_text, self.original_text)
        except Exception as e:
            logger.warning(f"评测历史保存失败: {e}")

    def mark_failed(self):
        self.status = "failed"

    def mark_cancelled(self):
        self._cancelled = True
        self.status = "cancelled"
        for phase in EvalPhase:
            if self.phases[phase]["status"] == EvalPhaseStatus.PENDING.value:
                self.phases[phase]["status"] = EvalPhaseStatus.CANCELLED.value
        self.overall_progress = 100.0
        self._save_to_disk()

    def _update_progress(self):
        total = len(EvalPhase)
        completed = sum(
            1 for p in EvalPhase
            if self.phases[p]["status"] in (
                EvalPhaseStatus.COMPLETED.value,
                EvalPhaseStatus.SKIPPED.value,
                EvalPhaseStatus.FAILED.value,
            )
        )
        self.overall_progress = round((completed / total) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "phases": {
                p.value: {
                    "status": self.phases[p]["status"],
                    "result": self.phase_results.get(p),
                    "error": self.phases[p].get("error"),
                }
                for p in EvalPhase
            },
            "overall_progress": self.overall_progress,
            "overall_score": self.overall_score,
            "sandtable_type": self.sandtable_type,
            "mode": self.mode,
            "platforms": self.platforms,
            "created_at": self.created_at,
        }

    @classmethod
    async def create(cls, sandtable_type: str = "", mode: str = "pipeline") -> "EvalSession":
        """创建会话并原子注册到全局存储"""
        await cls._cleanup_stale()
        session = cls.__new__(cls)
        session.__init_args__(sandtable_type, mode)
        async with _sessions_lock:
            _sessions[session.session_id] = session
        return session

    def __init_args__(self, sandtable_type: str = "", mode: str = "pipeline"):
        """内部初始化（不注册到全局存储，由 create() 统一注册）"""
        self.session_id: str = uuid.uuid4().hex[:12]
        self.status: str = "running"
        self._cancelled: bool = False
        self.phases: dict[EvalPhase, dict] = {}
        self.phase_results: dict[EvalPhase, dict] = {}
        self.overall_progress: float = 0.0
        self.overall_score: float | None = None
        self._event_queue: asyncio.Queue | None = None
        self.sandtable_type: str = sandtable_type
        self.mode: str = mode
        self.evaluated_text: str = ""
        self.original_text: str = ""
        self.platforms: list[str] = []
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self._created_ts: float = _now_ts()

        for phase in EvalPhase:
            self.phases[phase] = {"status": EvalPhaseStatus.PENDING.value}

    @classmethod
    async def get(cls, session_id: str) -> "EvalSession | None":
        async with _sessions_lock:
            return _sessions.get(session_id)

    @classmethod
    async def list_all(cls) -> list["EvalSession"]:
        async with _sessions_lock:
            return sorted(
                _sessions.values(),
                key=lambda s: s.created_at,
                reverse=True,
            )

    @classmethod
    async def remove(cls, session_id: str):
        async with _sessions_lock:
            _sessions.pop(session_id, None)

    @classmethod
    async def _cleanup_stale(cls):
        """移除超过 TTL 的过期会话，防止内存泄漏"""
        async with _sessions_lock:
            now = _now_ts()
            stale_ids = [
                sid for sid, s in _sessions.items()
                if (now - s._created_ts) > _SESSION_TTL_SECONDS
            ]
            for sid in stale_ids:
                del _sessions[sid]
            if stale_ids:
                logger.info(f"清理了 {len(stale_ids)} 个过期会话")
