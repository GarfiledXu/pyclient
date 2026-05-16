import sys
import os
from pathlib import Path
from loguru import logger
from .config import cfg, ConfigManager


class DualRotator:
    """组合切分判定器，支持按文件大小与每日固定时间点执行切分"""

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


class LogManager:
    @staticmethod
    def _make_formatter(sink_name: str, enable_color: bool = False):
        """格式化器生成工厂，根据日志级别选择预先固化的配置对象"""
        pipe_cfg = cfg.log.console if sink_name == "console" else cfg.log.file

        def formatter(record):
            fmt = pipe_cfg.formats.raw if record["level"].name == "RAW" else pipe_cfg.formats.default

            parts = []
            if fmt.show_time:
                parts.append(
                    "<green>{time:HH:mm:ss.SSS}</green>" if enable_color else "{time:HH:mm:ss.SSS}")
            if fmt.show_level:
                parts.append(
                    "<level>{level.name: <1.1}</level>" if enable_color else "{level.name: <1.1}")

            if fmt.show_details:
                meta = []
                if fmt.show_thread:
                    meta.append("[{thread.id: >5}]")
                if fmt.show_location:
                    meta.append("[{name: <8.8}:{line: >3}]")
                if fmt.show_module:
                    meta.append(
                        f"[{record['extra'].get('module', 'SYS'): <6.6}]")

                meta_str = " ".join(meta)
                if enable_color and pipe_cfg.use_dim_style:
                    parts.append(f"<dim>{meta_str}</dim>")
                else:
                    parts.append(meta_str)

            parts.append(
                "| <level>{message}</level>\n" if enable_color else "| {message}\n")
            return " ".join(parts)

        return formatter

    @classmethod
    def setup(cls):
        """配置并初始化 Loguru 日志挂载点"""
        logger.remove()
        logger.level("RAW", no=15, color="<blue><bold>")

        # 挂载 stdout 控制台
        if cfg.log.console.enable:
            logger.add(
                sys.stdout,
                format=cls._make_formatter("console", True),
                level=cfg.log.console.level,
                colorize=True
            )

        # 挂载本地日志文件
        if cfg.log.file.enable:
            root_dir = ConfigManager.get_root_dir()
            f_path = root_dir / cfg.log.file.path

            rot_val = None
            if cfg.log.file.size_mb > 0 or cfg.log.file.time:
                rot_val = DualRotator(cfg.log.file.size_mb, cfg.log.file.time)

            logger.add(
                str(f_path),
                format=cls._make_formatter("file", False),
                level=cfg.log.file.level,
                rotation=rot_val,
                retention=cfg.log.file.retention,
                compression=cfg.log.file.compression_format if cfg.log.file.compression_enable else None,
                enqueue=True,
                delay=True
            )
        return logger


log = LogManager.setup()
