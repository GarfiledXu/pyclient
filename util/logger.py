import sys
import os
import datetime
import queue
from pathlib import Path
from loguru import logger

# 兼容 Python 3.10 及以下版本
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("[警告] 请在 Python 3.10 环境下执行: pip install tomli")
        sys.exit(1)

# ==========================================
# 1. 路径与环境探测 (防 EXE 打包找不到文件)
# ==========================================


def get_app_dir() -> Path:
    """智能获取程序根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


APP_DIR = get_app_dir()
CONFIG_FILE = APP_DIR / "config.toml"
gui_log_queue = queue.Queue()

# ==========================================
# 2. 自定义双条件切分判定器
# ==========================================


class DualRotator:
    """支持 [大小] 与 [每天固定时间] 组合的切分器 (先到先得)"""

    def __init__(self, size_mb: float, at_time_str: str):
        self.size_limit = int(
            size_mb * 1024 * 1024) if size_mb > 0 else float('inf')
        self.time_limit = None
        if at_time_str:
            try:
                hour, min = map(int, at_time_str.split(":"))
                now = datetime.datetime.now()
                self.time_limit = now.replace(
                    hour=hour, minute=min, second=0, microsecond=0)
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
            self.time_limit += datetime.timedelta(days=1)
            return True
        return False

# ==========================================
# 3. 配置加载中心 (含极限防呆的 TOML 模板)
# ==========================================


class LogConfig:
    format_base = {}
    sinks = {}
    levels = {}

    @classmethod
    def load(cls):
        if not CONFIG_FILE.exists():
            cls._generate_default()
        try:
            with open(CONFIG_FILE, "rb") as f:
                data = tomllib.load(f).get("log", {})
                cls.format_base = data.get("format", {})
                cls.sinks = data.get("sinks", {})
                cls.levels = data.get("levels", {})
        except Exception as e:
            print(f"[警告] config.toml 解析失败，将使用默认规则: {e}")

    @staticmethod
    def _generate_default():
        content = """\
# ==============================================================================
# NVS 上位机客户端 - 日志核心配置文件
#
# 注意事项:
# 1. 路径分隔符请统一使用标准斜杠 "/" 
# 2. 修改配置后需重启软件方可生效
# ==============================================================================

[log.format]
# --- 全局显示开关 (Boolean: true/false) ---
show_time = true       # 是否显示时间戳 (HH:mm:ss.SSS)
show_level = true      # 是否显示日志等级 (单字符 D/I/W/E/R)
show_details = true    # 详情总开关 (设为 false 时，强制关闭下方所有项)
show_thread = true     # 是否显示线程 ID
show_location = true   # 是否显示代码调用位置 (文件名:行号)
show_module = true     # 是否显示业务标签 (如 [NET ])

[log.sinks.console]
# --- 终端控制台配置 ---
enable = true          # 是否在终端打印日志 (Boolean)
# 终端最低输出等级 (String)
# 可选枚举: "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL", "RAW"
level = "DEBUG"
use_dim_style = true   # 终端特有: 是否对元数据启用灰色弱化显示 (Boolean)

[log.sinks.file]
# --- 本地文件持久化配置 ---
enable = true          # 是否记录到文件 (Boolean)
# 文件落盘最低等级 (String)，通常建议设为 DEBUG 以保留完整追溯现场
# 可选枚举同上: "TRACE" ~ "RAW"
level = "DEBUG"
# 日志存储路径 (String)。支持相对路径(基于 exe 所在目录)或绝对路径。
path = "logs/nvs_app.log"

[log.sinks.file.rotation]
enable = true          # 是否开启自动切分 (Boolean)
# 按文件大小切分阈值 (Integer, 单位: MB)。设为 0 则关闭按大小切分。
size_mb = 50
# 每天定时切分时间 (String)。
# 格式要求: "HH:MM" (24小时制，如 "00:00" 为每天午夜)。填 "" 则关闭定时切分。
time = "00:00"

[log.sinks.file.retention]
enable = true          # 是否开启历史日志清理 (Boolean)
# 历史日志保留策略 (String)
# 格式要求: "<数字> <单位>"
# 可选单位: "days", "weeks", "months", "years" (按时间), 或者 "MB", "GB" (按总量)
# 配置示例: "7 days", "1 week", "100 MB"
rule = "7 days"

[log.sinks.file.compression]
enable = false         # 是否开启旧日志压缩归档 (Boolean)
# 压缩算法格式 (String)
# 可选枚举: "zip", "gz", "bz2", "xz", "lzma", "tar", "tar.gz", "tar.bz2", "tar.xz"
format = "zip"

# ==============================================================================
# 级别精细化覆盖 (Level Override)
# ==============================================================================
[log.levels.RAW]
# 针对底层 RAW 报文，强制关闭时间和细节，保持控制台数据流绝对纯净
show_time = false      # (Boolean)
show_details = false   # (Boolean)
"""
        try:
            CONFIG_FILE.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"[警告] 无法生成默认配置 config.toml: {e}")

# ==========================================
# 4. 格式化器工厂
# ==========================================


def make_formatter(sink_name: str, enable_color: bool = False):
    def formatter(record):
        cfg = LogConfig.format_base.copy()
        sink_cfg = LogConfig.sinks.get(sink_name, {})
        cfg.update(sink_cfg.get("override", {}))
        cfg.update(LogConfig.levels.get(record["level"].name, {}))

        parts = []
        if cfg.get("show_time"):
            parts.append(
                "<green>{time:HH:mm:ss.SSS}</green>" if enable_color else "{time:HH:mm:ss.SSS}")
        if cfg.get("show_level"):
            parts.append(
                "<level>{level.name: <1.1}</level>" if enable_color else "{level.name: <1.1}")

        if cfg.get("show_details"):
            meta = []
            if cfg.get("show_thread"):
                meta.append("[{thread.id: >5}]")
            if cfg.get("show_location"):
                meta.append("[{name: <8.8}:{line: >3}]")
            if cfg.get("show_module"):
                meta.append(f"[{record['extra'].get('module', 'SYS'): <6.6}]")

            meta_str = " ".join(meta)
            if enable_color and sink_cfg.get("use_dim_style", False):
                parts.append(f"<dim>{meta_str}</dim>")
            else:
                parts.append(meta_str)

        parts.append(
            "| <level>{message}</level>\n" if enable_color else "| {message}\n")
        return " ".join(parts)
    return formatter

# ==========================================
# 5. 管理器：Sink 挂载
# ==========================================


class LogManager:
    @classmethod
    def setup(cls):
        LogConfig.load()
        logger.remove()

        # 注册自定义的通信报文级别
        logger.level("RAW", no=15, color="<blue><bold>")

        # 挂载控制台
        con_cfg = LogConfig.sinks.get("console", {})
        if con_cfg.get("enable", True):
            logger.add(
                sys.stdout,
                format=make_formatter("console", True),
                level=con_cfg.get("level", "DEBUG"),
                colorize=True
            )

        # 挂载文件
        f_cfg = LogConfig.sinks.get("file", {})
        if f_cfg.get("enable", True):
            f_path = APP_DIR / f_cfg.get("path", "logs/nvs_app.log")

            rot_cfg = f_cfg.get("rotation", {})
            rot_val = DualRotator(rot_cfg.get("size_mb", 0), rot_cfg.get(
                "time", "")) if rot_cfg.get("enable", True) else None

            ret_cfg = f_cfg.get("retention", {})
            ret_val = ret_cfg.get("rule", "7 days") if ret_cfg.get(
                "enable", True) else None

            com_cfg = f_cfg.get("compression", {})
            com_val = com_cfg.get("format", "zip") if com_cfg.get(
                "enable", False) else None

            logger.add(
                str(f_path),
                format=make_formatter("file", False),
                level=f_cfg.get("level", "DEBUG"),
                rotation=rot_val,
                retention=ret_val,
                compression=com_val,
                enqueue=True,
                delay=True
            )

        # 挂载 GUI (为后续图形化预留)
        logger.add(
            lambda msg: gui_log_queue.put((str(msg), msg.record)),
            format=make_formatter("gui", False),
            level="DEBUG"
        )

        return logger


# 全局暴露单例
log = LogManager.setup()


def format_packet(header: bytes, cmd: int, payload: bytes, crc: bytes) -> str:
    """报文格式化工具"""
    h_str = header.hex(' ').upper()
    p_str = payload.hex(' ').upper() if payload else "N/A"
    c_str = crc.hex(' ').upper()
    return f"HDR[{h_str}] CMD[{cmd:02X}] DATA[{p_str}] CRC[{c_str}]"
