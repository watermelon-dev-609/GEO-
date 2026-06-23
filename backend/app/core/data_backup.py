"""数据自动备份 — 每日轮转备份 data/ 目录，保留最近7天"""

import logging
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = ".backups"
MAX_BACKUPS = 7  # 保留最近7天


def get_backup_dir(data_dir: Path | None = None) -> Path:
    """获取备份目录路径"""
    if data_dir is None:
        from app.utils.config import get_data_dir
        data_dir = get_data_dir()
    backup_dir = data_dir / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def create_backup(data_dir: Path | None = None) -> dict:
    """创建一次数据备份（ZIP压缩）

    Returns:
        {"backup_file": str, "size_kb": float, "files_count": int}
    """
    if data_dir is None:
        from app.utils.config import get_data_dir
        data_dir = get_data_dir()

    backup_dir = get_backup_dir(data_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"geo_backup_{timestamp}.zip"

    files_count = 0
    try:
        with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in data_dir.rglob("*"):
                if f.is_file() and BACKUP_DIR_NAME not in str(f.relative_to(data_dir)):
                    zf.write(f, f.relative_to(data_dir))
                    files_count += 1

        size_kb = backup_file.stat().st_size / 1024
        logger.info(f"数据备份完成: {backup_file.name} ({size_kb:.1f} KB, {files_count} 文件)")

        # 清理旧备份（保留最近7个）
        cleanup_old_backups(backup_dir)

        return {
            "backup_file": str(backup_file),
            "size_kb": round(size_kb, 1),
            "files_count": files_count,
        }
    except Exception as e:
        logger.error(f"数据备份失败: {e}")
        raise


def cleanup_old_backups(backup_dir: Path | None = None) -> list[str]:
    """清理超过7天的旧备份，保留最近7个"""
    if backup_dir is None:
        from app.utils.config import get_data_dir
        backup_dir = get_data_dir() / BACKUP_DIR_NAME

    backups = sorted(backup_dir.glob("geo_backup_*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = []
    for old in backups[MAX_BACKUPS:]:
        try:
            old.unlink()
            removed.append(old.name)
            logger.info(f"清理旧备份: {old.name}")
        except Exception as e:
            logger.warning(f"清理旧备份失败 {old.name}: {e}")
    return removed


def list_backups(data_dir: Path | None = None) -> list[dict]:
    """列出所有备份"""
    if data_dir is None:
        from app.utils.config import get_data_dir
        data_dir = get_data_dir()

    backup_dir = get_backup_dir(data_dir)
    backups = sorted(backup_dir.glob("geo_backup_*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)

    result = []
    for b in backups:
        stat = b.stat()
        result.append({
            "name": b.name,
            "size_kb": round(stat.st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "age_days": round((datetime.now() - datetime.fromtimestamp(stat.st_mtime)).total_seconds() / 86400, 1),
        })
    return result


def restore_backup(backup_name: str, data_dir: Path | None = None) -> dict:
    """从备份恢复数据（覆盖当前 data/ 目录）

    警告：此操作会覆盖当前数据！
    """
    if data_dir is None:
        from app.utils.config import get_data_dir
        data_dir = get_data_dir()

    backup_dir = get_backup_dir(data_dir)
    backup_file = backup_dir / backup_name

    if not backup_file.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup_name}")

    restored_count = 0
    try:
        with zipfile.ZipFile(backup_file, "r") as zf:
            zf.extractall(data_dir)
            restored_count = len(zf.namelist())

        logger.info(f"数据恢复完成: {backup_name} ({restored_count} 文件)")
        return {
            "restored_from": backup_name,
            "files_restored": restored_count,
            "restored_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"数据恢复失败: {e}")
        raise


def register_backup_job():
    """将每日备份注册到定时调度器"""
    try:
        from app.core.scheduler import get_scheduler
        from app.core.data_backup import create_backup

        scheduler = get_scheduler()
        scheduler.add_job(
            create_backup,
            trigger="cron",
            hour=2,  # 凌晨2点执行
            minute=0,
            id="daily_data_backup",
            name="每日数据备份",
            replace_existing=True,
        )
        logger.info("每日数据备份任务已注册（每天凌晨2:00）")
    except Exception as e:
        logger.warning(f"注册备份任务失败（调度器可能未启动）: {e}")
