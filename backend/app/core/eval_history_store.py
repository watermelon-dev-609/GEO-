"""评测历史持久化存储 — JSON文件存储层"""

from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 数据目录：backend/data/evaluations/
def _get_history_dir() -> Path:
    from app.utils.config import get_data_dir
    d = get_data_dir() / "evaluations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(session, evaluated_text: str = "", original_text: str = "") -> Path:
    """将评测会话保存为JSON文件"""
    data = session.to_dict()
    # 附加评测上下文
    platforms = getattr(session, 'platforms', [])
    if hasattr(platforms, '__iter__') and not isinstance(platforms, (str, bytes)):
        platforms = [p.value if hasattr(p, 'value') else str(p) for p in platforms]
    data["evaluated_text"] = evaluated_text[:5000] if evaluated_text else ""
    data["original_text"] = original_text[:5000] if original_text else ""
    data["platforms"] = platforms
    data["mode"] = getattr(session, 'mode', 'pipeline')

    filepath = _get_history_dir() / f"{session.session_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"评测历史已保存: {filepath}")
    return filepath


def load_all_sessions() -> list[dict]:
    """加载所有评测历史，按时间倒序"""
    d = _get_history_dir()
    sessions = []
    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                sessions.append(json.load(fp))
        except Exception as e:
            logger.warning(f"跳过损坏的历史文件 {f.name}: {e}")
    return sessions


def load_session(session_id: str) -> dict | None:
    """加载单个评测历史"""
    filepath = _get_history_dir() / f"{session_id}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"无法读取历史文件 {session_id}: {e}")
        return None


def delete_session(session_id: str) -> bool:
    """删除评测历史文件"""
    filepath = _get_history_dir() / f"{session_id}.json"
    if not filepath.exists():
        return False
    filepath.unlink()
    logger.info(f"评测历史已删除: {session_id}")
    return True
