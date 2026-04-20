import sys
import queue
from pathlib import Path
from loguru import logger

# ==========================================
# 1. 动态配置中心 (单例类)
# ==========================================


class LogConfig:
    """
    日志行为控制器。
    支持直接操作变量：LogConfig.show_time = False
    也支持批量更新：LogConfig.update(show_details=False, use_dim_style=True)
    """
    # 【总开关】控制中间所有元数据 (Thread, Location, Module)
    show_details = True

    # 【分项开关】仅在 show_details 为 True 时有效
    show_time = True   # 时间戳 (HH:mm:ss.SSS)
    show_level = True   # 等级单字符 (D/I/W/E/R)
    show_thread = True   # 线程ID
    show_location = True   # 代码位置 (文件名:行号)
    show_module = True   # 业务标签 (NET/OCR等)

    # 【样式开关】
    use_dim_style = True   # 是否灰化元数据

    @classmethod
    def update(cls, **kwargs):
        """批量更新配置接口"""
        for key, value in kwargs.items():
            if hasattr(cls, key):
                setattr(cls, key, value)


# GUI 异步日志队列
gui_log_queue = queue.Queue()

# ==========================================
# 2. 动态格式化渲染器
# ==========================================


def _get_dynamic_format(record):
    """
    像拼乐高一样构建每一行日志。
    由于是每行动态渲染，所以修改 LogConfig 属性会立即生效。
    """
    parts = []

    # 1. 时间戳区 (固定绿色)
    if LogConfig.show_time:
        parts.append("<green>{time:HH:mm:ss.SSS}</green>")

    # 2. 级别区 (跟随等级颜色)
    if LogConfig.show_level:
        parts.append("<level>{level.name: <1.1}</level>")

    # 3. 元数据区 (受总开关保护)
    if LogConfig.show_details:
        meta = []
        if LogConfig.show_thread:
            meta.append("[{thread.id: >5}]")
        if LogConfig.show_location:
            meta.append("[{name: <8.8}:{line: >3}]")
        if LogConfig.show_module:
            meta_val = record["extra"].get("module", "SYS   ")
            meta.append(f"[{meta_val: <6.6}]")

        if meta:
            # 应用灰化逻辑
            s, e = ("<dim>", "</dim>") if LogConfig.use_dim_style else ("", "")
            parts.append(f"{s}{' '.join(meta)}{e}")

    # 4. 消息主体 (使用管道符 | 隔离)
    parts.append("| <level>{message}</level>\n")

    return " ".join(parts)

# ==========================================
# 3. 日志管理器 (引擎初始化)
# ==========================================


class LogManager:
    @classmethod
    def setup(cls):
        """核心初始化逻辑"""
        logger.remove()

        # A. 配置等级颜色 (INFO 改为莫兰迪绿，RAW 改为深蓝)
        logger.level("INFO", color="<fg #A9DFBF><bold>")
        logger.level("RAW", no=15, color="<blue><bold>")

        # B. 挂载控制台 (启用异步非阻塞模式)
        logger.add(
            sys.stdout,
            format=_get_dynamic_format,
            level="DEBUG",
            colorize=True,
            enqueue=True
        )

        # C. 挂载本地文件 (文件日志不随配置变动，始终全量记录)
        log_path = Path("logs") / "debug_client_{time:YYYY-MM-DD}.log"
        logger.add(
            log_path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level.name: <8} | {thread.id: >5} | {name}:{line} | {message}\n",
            level="DEBUG",
            rotation="00:00",
            retention="7 days",
            enqueue=True,
            delay=True
        )

        # D. 挂载 GUI 队列
        logger.add(
            cls._gui_sink,
            format=_get_dynamic_format,
            level="INFO"
        )

        return logger

    @staticmethod
    def _gui_sink(message):
        """将处理好的文本连同 record 原始数据一起推入队列"""
        gui_log_queue.put((str(message), message.record))

# ==========================================
# 4. 外部调用接口
# ==========================================


# 导出全局唯一实例
log = LogManager.setup()


def format_packet(header: bytes, cmd: int, payload: bytes, crc: bytes) -> str:
    """底层报文美化工具"""
    h_str = header.hex(' ').upper()
    p_str = payload.hex(' ').upper() if payload else "N/A"
    c_str = crc.hex(' ').upper()
    return f"HDR[{h_str}] CMD[{cmd:02X}] DATA[{p_str}] CRC[{c_str}]"

# ==========================================
# 5. 使用演示 (Usage Demonstration)
# ==========================================


if __name__ == "__main__":
    # --- 演示 A：全量模式 ---
    log.bind(module="NET").info("开始建立 TCP 握手")

    # --- 演示 B：批量更新配置 (隐藏细节) ---
    LogConfig.update(show_details=False, show_time=True)
    log.warning("检测到连接不稳定 (当前已隐藏详情)")
    log.info("检测到连接不稳定 (当前已隐藏详情)")
    log.debug("检测到连接不稳定 (当前已隐藏详情)")
    log.error("检测到连接不稳定 (当前已隐藏详情)")

    # --- 演示 C：极简模式 (纯净报文) ---
    LogConfig.update(show_time=False, show_level=True)
    log.log("RAW", "HEX -> {}", format_packet(b'\xAA', 0x05, b'\x01\x02', b'\xFF'))
