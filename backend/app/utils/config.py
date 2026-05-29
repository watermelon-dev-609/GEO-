"""配置加载工具 — 带内存缓存，避免每次请求重复 I/O"""

import os
import time
import yaml
import threading
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app/utils -> backend
CONFIG_DIR = ROOT_DIR / "config"

_settings_cache: dict[str, Any] | None = None
_settings_cache_ts: float = 0
_api_keys_cache: dict[str, Any] | None = None
_api_keys_cache_ts: float = 0
_cache_lock = threading.Lock()
CACHE_TTL = 10.0  # 缓存有效期 10 秒，平衡性能和热更新


def load_settings() -> dict[str, Any]:
    """加载主配置文件（10s 缓存）"""
    global _settings_cache, _settings_cache_ts
    now = time.time()
    if _settings_cache is not None and (now - _settings_cache_ts) < CACHE_TTL:
        return _settings_cache
    settings_path = CONFIG_DIR / "settings.yaml"
    result = {}
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f) or {}
    with _cache_lock:
        _settings_cache = result
        _settings_cache_ts = now
    return result


def _load_dotenv() -> dict[str, str]:
    """从 backend/.env 加载环境变量（简单的 key=value 解析）"""
    env_path = ROOT_DIR / ".env"
    env_vars = {}
    if not env_path.exists():
        return env_vars
    import re
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$', line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if (val.startswith('"') and val.endswith('"')) or \
                   (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                env_vars[key] = val
    return env_vars


def _resolve_placeholders(data: Any, env_vars: dict[str, str]) -> Any:
    """递归解析 ${VAR} 占位符"""
    if isinstance(data, str):
        import re
        seen = set()
        def _repl(m):
            return env_vars.get(m.group(1), m.group(0))
        result = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', _repl, data)
        return result
    if isinstance(data, dict):
        return {k: _resolve_placeholders(v, env_vars) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_placeholders(v, env_vars) for v in data]
    return data


def load_api_keys() -> dict[str, Any]:
    """加载API Key配置（10s 缓存）"""
    global _api_keys_cache, _api_keys_cache_ts
    now = time.time()
    if _api_keys_cache is not None and (now - _api_keys_cache_ts) < CACHE_TTL:
        return _api_keys_cache
    keys_path = CONFIG_DIR / "api_keys.yaml"
    config = {}
    if keys_path.exists():
        with open(keys_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    env_vars = _load_dotenv()
    if env_vars:
        config = _resolve_placeholders(config, env_vars)
    with _cache_lock:
        _api_keys_cache = config
        _api_keys_cache_ts = now
    return config


def invalidate_config_cache():
    """强制刷新配置缓存（API Key 变更后调用）"""
    global _settings_cache, _api_keys_cache, _settings_cache_ts, _api_keys_cache_ts
    with _cache_lock:
        _settings_cache = None
        _api_keys_cache = None
        _settings_cache_ts = 0
        _api_keys_cache_ts = 0


def get_data_dir() -> Path:
    """获取数据目录绝对路径"""
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    path = Path(data_dir)
    if not path.is_absolute():
        path = ROOT_DIR / data_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_enterprise_name() -> str:
    """从配置读取企业全称"""
    settings = load_settings()
    return settings.get("system", {}).get("enterprise_name", "武汉微艺达智能科技有限公司")


def get_enterprise_location() -> str:
    """从配置读取企业所在地"""
    settings = load_settings()
    return settings.get("system", {}).get("enterprise_location", "武汉")
