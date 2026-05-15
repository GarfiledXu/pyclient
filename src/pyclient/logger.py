import sys
import os
from loguru import logger
from .config import cfg  # 导入已合并好的全局配置
from pathlib import Path  # <--- 补上这一行

# ==========================================
# 1. 自定义切分判定器 (保持你原有的优秀逻辑)
# ==========================================


class DualRotator:
    """支持 [大小] 与 [每天固定时间] 组合的切分器"""

    def __init__(self, size_mb: float, at_time_str: str):
        self.size_limit = int(
            size_mb * 1024 * 1024) if size_mb > 0 else float('inf')
        self.time_limit = None
        if at_time_str:
            import datetime
            try:
                hour, minute = map(int, at_time_str.split(":"))
                now = datetime.datetime.now()
                self.time_limit = now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0)
                if now >= self.time_limit:
                    self.time_limit += datetime.timedelta(days=1)
            except Exception:
                pass

    def __call__(self, message, file) -> bool:
        if self.size_limit != float('inf'):
            file.seek(0, os.SEEK_END)
            if file.tell() + len(message) >= self.size_limit:
                return True
        if self.time_limit and message.record["time"].timestamp() >= self.time_limit.timestamp():
            import datetime
            self.time_limit += datetime.timedelta(days=1)
            return True
        return False

# ==========================================
# 2. 日志管理器
# ==========================================


class LogManager:
    @staticmethod
    def _make_formatter(sink_name: str, enable_color: bool = False):
        """格式化工厂：从 cfg 中动态提取显示规则"""
        log_cfg = cfg.get("log", {})
        format_cfg = log_cfg.get("format", {})
        sink_cfg = log_cfg.get("sinks", {}).get(sink_name, {})

        def formatter(record):
            # 合并覆盖规则：全局 < Sink特定 < 级别特定
            active_cfg = format_cfg.copy()
            active_cfg.update(sink_cfg.get("override", {}))
            active_cfg.update(log_cfg.get(
                "levels", {}).get(record["level"].name, {}))

            parts = []
            if active_cfg.get("show_time"):
                parts.append(
                    "<green>{time:HH:mm:ss.SSS}</green>" if enable_color else "{time:HH:mm:ss.SSS}")
            if active_cfg.get("show_level"):
                parts.append(
                    "<level>{level.name: <1.1}</level>" if enable_color else "{level.name: <1.1}")

            if active_cfg.get("show_details"):
                meta = []
                if active_cfg.get("show_thread"):
                    meta.append("[{thread.id: >5}]")
                if active_cfg.get("show_location"):
                    meta.append("[{name: <8.8}:{line: >3}]")
                if active_cfg.get("show_module"):
                    meta.append(
                        f"[{record['extra'].get('module', 'SYS'): <6.6}]")

                meta_str = " ".join(meta)
                if enable_color and sink_cfg.get("use_dim_style", False):
                    parts.append(f"<dim>{meta_str}</dim>")
                else:
                    parts.append(meta_str)

            parts.append(
                "| <level>{message}</level>\n" if enable_color else "| {message}\n")
            return " ".join(parts)
        return formatter

    @classmethod
    def setup(cls):
        """启动配置：由 cfg 驱动全链路挂载"""
        log_data = cfg.get("log", {})
        logger.remove()

        # 1. 注册特殊级别
        logger.level("RAW", no=15, color="<blue><bold>")

        # 2. 挂载控制台
        con_cfg = log_data.get("sinks", {}).get("console", {})
        if con_cfg.get("enable", True):
            logger.add(
                sys.stdout,
                format=cls._make_formatter("console", True),
                level=con_cfg.get("level", "DEBUG"),
                colorize=True
            )

        # 3. 挂载文件
        f_cfg = log_data.get("sinks", {}).get("file", {})
        if f_cfg.get("enable", True):
            # 路径处理：基于根目录定位日志
            root_dir = Path(__file__).resolve().parents[2]
            f_path = root_dir / f_cfg.get("path", "logs/app.log")

            rot_cfg = f_cfg.get("rotation", {})
            rot_val = DualRotator(rot_cfg.get("size_mb", 0), rot_cfg.get(
                "time", "")) if rot_cfg.get("enable") else None

            logger.add(
                str(f_path),
                format=cls._make_formatter("file", False),
                level=f_cfg.get("level", "DEBUG"),
                rotation=rot_val,
                retention=f_cfg.get("retention", {}).get("rule", "7 days"),
                compression=f_cfg.get("compression", {}).get("format", "zip") if f_cfg.get(
                    "compression", {}).get("enable") else None,
                enqueue=True,
                delay=True
            )

        return logger


# --- 全局暴露唯一 log 实例 ---
log = LogManager.setup()
