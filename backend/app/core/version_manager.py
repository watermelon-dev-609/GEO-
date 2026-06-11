"""内容版本管理 — 优化历史存档、版本对比、一键回滚"""

from __future__ import annotations
import json
import difflib
import hashlib
import os
import tempfile
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field

from app.utils.config import load_settings

logger = logging.getLogger(__name__)


@dataclass
class VersionRecord:
    version_id: str
    text_id: str
    title: str
    content: str
    platform: str = ""
    version_num: int = 1
    created_at: str = ""
    word_count: int = 0
    tags: list[str] = field(default_factory=list)
    notes: str = ""


def _get_versions_dir() -> Path:
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    base = Path(data_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent.parent / data_dir
    vdir = base / "versions"
    vdir.mkdir(parents=True, exist_ok=True)
    return vdir


def _get_text_versions_file(text_id: str) -> Path:
    return _get_versions_dir() / f"{text_id}.json"


def _atomic_write(filepath: Path, data: list[dict]):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                      delete=False, dir=filepath.parent) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, str(filepath))


class VersionManager:
    """内容版本管理器"""

    @staticmethod
    def save_version(
        text_id: str,
        content: str,
        title: str = "",
        platform: str = "",
        tags: list[str] | None = None,
        notes: str = "",
    ) -> VersionRecord:
        """保存一个新版本"""
        filepath = _get_text_versions_file(text_id)
        existing = []
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)

        version_num = len(existing) + 1
        version_id = hashlib.md5(f"{text_id}:{version_num}:{time.time()}".encode()).hexdigest()[:12]

        record = VersionRecord(
            version_id=version_id,
            text_id=text_id,
            title=title or f"版本{version_num}",
            content=content,
            platform=platform,
            version_num=version_num,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            word_count=len(content),
            tags=tags or [],
            notes=notes,
        )

        existing.append({
            "version_id": record.version_id,
            "text_id": record.text_id,
            "title": record.title,
            "content": record.content,
            "platform": record.platform,
            "version_num": record.version_num,
            "created_at": record.created_at,
            "word_count": record.word_count,
            "tags": record.tags,
            "notes": record.notes,
        })

        # 最多保留 50 个版本
        if len(existing) > 50:
            existing = existing[-50:]

        _atomic_write(filepath, existing)
        return record

    @staticmethod
    def list_versions(text_id: str) -> list[VersionRecord]:
        """列出文本的所有版本"""
        filepath = _get_text_versions_file(text_id)
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [
            VersionRecord(
                version_id=v["version_id"],
                text_id=v.get("text_id", text_id),
                title=v.get("title", ""),
                content=v.get("content", ""),
                platform=v.get("platform", ""),
                version_num=v.get("version_num", i + 1),
                created_at=v.get("created_at", ""),
                word_count=v.get("word_count", 0),
                tags=v.get("tags", []),
                notes=v.get("notes", ""),
            )
            for i, v in enumerate(data)
        ]

    @staticmethod
    def get_version(text_id: str, version_id: str) -> VersionRecord | None:
        """获取指定版本"""
        versions = VersionManager.list_versions(text_id)
        for v in versions:
            if v.version_id == version_id:
                return v
        return None

    @staticmethod
    def rollback(text_id: str, version_id: str) -> VersionRecord | None:
        """回滚到指定版本 — 将目标版本内容保存为新版本"""
        target = VersionManager.get_version(text_id, version_id)
        if not target:
            return None
        return VersionManager.save_version(
            text_id=text_id,
            content=target.content,
            title=f"回滚至{target.title}",
            platform=target.platform,
            tags=["回滚"],
            notes=f"从版本{target.version_num}回滚",
        )

    @staticmethod
    def compare(text_id: str, version_id1: str, version_id2: str) -> dict:
        """对比两个版本"""
        v1 = VersionManager.get_version(text_id, version_id1)
        v2 = VersionManager.get_version(text_id, version_id2)
        if not v1 or not v2:
            return {"error": "版本不存在"}

        diff = list(difflib.unified_diff(
            v1.content.splitlines(keepends=True),
            v2.content.splitlines(keepends=True),
            fromfile=f"v{v1.version_num}: {v1.title}",
            tofile=f"v{v2.version_num}: {v2.title}",
            lineterm="",
        ))

        return {
            "version1": {"id": v1.version_id, "num": v1.version_num, "title": v1.title, "word_count": v1.word_count, "created_at": v1.created_at},
            "version2": {"id": v2.version_id, "num": v2.version_num, "title": v2.title, "word_count": v2.word_count, "created_at": v2.created_at},
            "diff_lines": diff,
            "added_lines": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
            "removed_lines": sum(1 for l in diff if l.startswith("-") and not l.startswith("---")),
            "word_diff": v2.word_count - v1.word_count,
        }

    @staticmethod
    def delete_version(text_id: str, version_id: str) -> bool:
        """删除指定版本"""
        filepath = _get_text_versions_file(text_id)
        if not filepath.exists():
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        before = len(data)
        data = [v for v in data if v["version_id"] != version_id]
        if len(data) == before:
            return False
        _atomic_write(filepath, data)
        return True
