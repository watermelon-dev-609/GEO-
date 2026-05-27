"""配置加载工具"""

import yaml
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app/utils -> backend
CONFIG_DIR = ROOT_DIR / "config"


def load_settings() -> dict[str, Any]:
    """加载主配置文件"""
    settings_path = CONFIG_DIR / "settings.yaml"
    if not settings_path.exists():
        return {}
    with open(settings_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_api_keys() -> dict[str, Any]:
    """加载API Key配置"""
    keys_path = CONFIG_DIR / "api_keys.yaml"
    if not keys_path.exists():
        return {}
    with open(keys_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_data_dir() -> Path:
    """获取数据目录绝对路径"""
    settings = load_settings()
    data_dir = settings.get("system", {}).get("data_dir", "./data")
    path = Path(data_dir)
    if not path.is_absolute():
        path = ROOT_DIR / data_dir
    path.mkdir(parents=True, exist_ok=True)
    return path
