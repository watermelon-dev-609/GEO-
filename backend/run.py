"""一键启动脚本 - GEO生成式搜索优化系统"""

import subprocess
import sys
import os
from pathlib import Path

# 修复 PyTorch scikit-learn OpenMP DLL 冲突导致 segfault 的问题
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

BACKEND_DIR = Path(__file__).resolve().parent


def check_dependencies():
    """检查Python依赖"""
    print("[1/3] 检查Python依赖...")
    try:
        import fastapi
        import uvicorn
        import yaml
        print("  [OK] 核心依赖已安装")
    except ImportError:
        print("  [X] 依赖未安装，正在安装...")
        req_path = BACKEND_DIR / "requirements.txt"
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_path)])
        print("  [OK] 依赖安装完成")


def check_config():
    """检查配置文件"""
    print("[2/3] 检查配置文件...")
    keys_path = BACKEND_DIR / "config" / "api_keys.yaml"
    example_path = BACKEND_DIR / "config" / "api_keys.yaml.example"
    if not keys_path.exists():
        print(f"  [!] api_keys.yaml 不存在，从示例文件复制...")
        import shutil
        shutil.copy(example_path, keys_path)
        print(f"  [OK] 已创建 api_keys.yaml，请编辑填入API Key: {keys_path}")
    else:
        print("  [OK] api_keys.yaml 已就绪")


def start_server():
    """启动FastAPI服务"""
    print("[3/3] 启动GEO优化系统服务...")
    print(f"  后端地址: http://127.0.0.1:8000")
    print(f"  API文档:  http://127.0.0.1:8000/docs")
    print(f"  按 Ctrl+C 停止服务\n")
    uvicorn_run()


def uvicorn_run():
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    print("=" * 56)
    print("  GEO生成式搜索优化系统 v2.0.0-personal")
    print("  武汉微艺达智能科技有限公司")
    print("=" * 56 + "\n")

    check_dependencies()
    check_config()
    start_server()
