"""模板文件监控 — 基于 watchdog 实时监听 YAML 模板变更

替代/补充原有的 60s TTL 轮询缓存，实现：
- 文件系统事件驱动的秒级缓存刷新
- 防抖处理（合并连续写入事件）
- 变更后自动预加载模板
- 可选：变更后自动触发适配流水线

Windows 兼容：watchdog 在 Windows 上使用 ReadDirectoryChangesW API。
"""

import asyncio
import logging
import hashlib
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 模块级单例 ──

_watcher: "TemplateFileWatcher | None" = None
_watcher_lock = threading.Lock()
_main_event_loop: "asyncio.AbstractEventLoop | None" = None  # 主线程事件循环引用


def _get_templates_dir() -> Path:
    """获取平台模板目录的绝对路径"""
    from app.utils.config import ROOT_DIR
    templates_dir = ROOT_DIR / "data" / "platform_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def _load_watchdog_config() -> dict[str, Any]:
    """加载 watchdog 相关配置"""
    try:
        from app.utils.config import load_settings
        settings = load_settings()
        return settings.get("watchdog", {})
    except Exception:
        return {}


class TemplateFileWatcher:
    """基于 watchdog 的模板文件监控器。

    监听 data/platform_templates/ 目录下的 YAML 文件变更，
    在文件修改/创建/删除时自动刷新模板缓存。
    """

    def __init__(self):
        self._observer = None
        self._event_handler = None
        self._watching = False
        self._watch_dir: Path | None = None
        self._last_event: dict[str, Any] = {}
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._debounce_lock = threading.Lock()
        self._stop_event = threading.Event()

    # ── 公开 API ──

    def start(self) -> bool:
        """启动文件监控。

        Returns:
            True 如果成功启动，False 如果已在运行或启动失败
        """
        global _main_event_loop

        if self._watching:
            logger.debug("Watchdog 已在运行，跳过重复启动")
            return False

        config = _load_watchdog_config()
        if not config.get("enabled", True):
            logger.info("Watchdog 在配置中被禁用")
            return False

        # 捕获主线程事件循环（供 watchdog daemon 线程跨线程调度用）
        try:
            _main_event_loop = asyncio.get_running_loop()
            logger.debug("已捕获主事件循环引用")
        except RuntimeError:
            _main_event_loop = None
            logger.debug("未检测到运行中的事件循环")

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            logger.warning("watchdog 库未安装，回退到 TTL 轮询模式")
            return False

        watch_dir = _get_templates_dir()
        self._watch_dir = watch_dir
        self._stop_event.clear()

        # 创建事件处理器
        watcher_ref = self  # 闭包引用

        class _TemplateEventHandler(FileSystemEventHandler):
            def on_modified(self, event: FileSystemEvent):
                watcher_ref._on_file_event("modified", event)

            def on_created(self, event: FileSystemEvent):
                watcher_ref._on_file_event("created", event)

            def on_deleted(self, event: FileSystemEvent):
                watcher_ref._on_file_event("deleted", event)

            def on_moved(self, event: FileSystemEvent):
                watcher_ref._on_file_event("moved", event)

        self._event_handler = _TemplateEventHandler()

        # 创建并启动 Observer
        self._observer = Observer()
        self._observer.schedule(self._event_handler, str(watch_dir), recursive=False)
        self._observer.start()

        self._watching = True
        logger.info(f"Watchdog 已启动，监控目录: {watch_dir}")
        return True

    def stop(self):
        """停止文件监控"""
        if not self._watching:
            return

        # 取消所有待执行的防抖定时器
        with self._debounce_lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()

        if self._observer:
            self._observer.stop()
            try:
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._observer = None

        self._event_handler = None
        self._watching = False
        self._stop_event.set()
        logger.info("Watchdog 已停止")

    def get_status(self) -> dict[str, Any]:
        """获取当前监控状态"""
        return {
            "watching": self._watching,
            "watched_dir": str(self._watch_dir) if self._watch_dir else "",
            "last_event": self._last_event,
            "debounce_pending": len(self._debounce_timers),
        }

    # ── 内部事件处理 ──

    def _on_file_event(self, event_type: str, event):
        """处理文件系统事件（在 watchdog 线程中调用）"""
        src_path = event.src_path if hasattr(event, 'src_path') else str(event)

        # 只处理 YAML 文件
        path = Path(src_path)
        if path.suffix not in (".yaml", ".yml"):
            return

        # 只处理平台模板目录下的直接文件（不递归）
        if path.parent != self._watch_dir:
            return

        filename = path.name
        logger.debug(f"Watchdog 事件: {event_type} -> {filename}")

        self._last_event = {
            "type": event_type,
            "file": filename,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 删除事件无需防抖，直接处理
        if event_type == "deleted":
            self._handle_change(filename, event_type)
            return

        # 修改/创建/移动事件需要防抖（合并编辑器的连续写入）
        self._debounce(filename, event_type)

    def _debounce(self, filename: str, event_type: str):
        """防抖处理：在文件稳定后（无新事件）才触发处理"""
        config = _load_watchdog_config()
        debounce_seconds = config.get("debounce_seconds", 2.0)

        with self._debounce_lock:
            # 取消该文件的旧定时器
            old_timer = self._debounce_timers.pop(filename, None)
            if old_timer:
                old_timer.cancel()

            # 创建新定时器
            timer = threading.Timer(debounce_seconds, self._handle_change, args=[filename, event_type])
            timer.daemon = True
            self._debounce_timers[filename] = timer
            timer.start()

    def _handle_change(self, filename: str, event_type: str):
        """防抖后实际处理文件变更"""
        # 从防抖字典中移除
        with self._debounce_lock:
            self._debounce_timers.pop(filename, None)

        platform_id = Path(filename).stem  # e.g. "wenxin" from "wenxin.yaml"
        file_path = self._watch_dir / filename

        # ── 1. 刷新模板缓存 ──
        config = _load_watchdog_config()
        if config.get("on_change_invalidate_cache", True):
            try:
                from app.core.template_engine import invalidate_cache, load_all_templates
                invalidate_cache()
                # 预加载所有模板到缓存
                load_all_templates()
                logger.info(f"Watchdog: 模板缓存已刷新 (触发文件: {filename})")
            except Exception as e:
                logger.error(f"Watchdog: 刷新缓存失败: {e}")
                return

        # ── 2. 可选：自动触发适配流水线 ──
        if event_type != "deleted" and config.get("on_change_trigger_adaptation", False):
            global _main_event_loop
            try:
                from app.core.adaptation_pipeline import trigger_from_yaml_change

                # 计算文件哈希用于变更追踪
                old_hash = ""
                new_hash = ""
                if file_path.exists():
                    try:
                        new_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
                    except Exception:
                        pass

                # 使用启动时捕获的主事件循环跨线程调度
                loop = _main_event_loop
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        trigger_from_yaml_change(platform_id, str(file_path), old_hash, new_hash),
                        loop,
                    )
                    logger.info(f"Watchdog: 已调度适配流水线触发 (平台={platform_id})")
                else:
                    logger.debug(f"Watchdog: 主事件循环不可用，跳过适配触发 (平台={platform_id})")
            except Exception as e:
                logger.warning(f"Watchdog: 自动触发适配流水线失败: {e}")


# ── 模块级便捷函数 ──


def start_watcher() -> bool:
    """启动全局 watchdog 实例"""
    global _watcher
    with _watcher_lock:
        if _watcher is None:
            _watcher = TemplateFileWatcher()
        return _watcher.start()


def stop_watcher():
    """停止全局 watchdog 实例"""
    global _watcher
    with _watcher_lock:
        if _watcher is not None:
            _watcher.stop()
            _watcher = None


def get_watcher_status() -> dict[str, Any]:
    """获取 watchdog 状态（用于 API 查询）"""
    global _watcher
    if _watcher is not None:
        return _watcher.get_status()
    return {"watching": False, "watched_dir": "", "last_event": {}, "debounce_pending": 0}
