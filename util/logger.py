"""
模块：src/debug_client/core/logger.py
职责：全局日志与配置中心。
特性：
  - 矩阵式绝对对齐，去除了多余的色彩割裂，使用统一的等级颜色渲染整行。
  - 异步无阻塞写入，保护高频网络收发与增量 IO 解析。
  - 基于 extra[module] 的路由分发与上下文隔离。
  - 支持跨线程 GUI 桥接。
"""

import sys
import queue
from pathlib import Path
from loguru import logger

# ==========================================
# 1. 全局资源与格式定义
# ==========================================

# GUI 异步日志队列，用于将后台日志安全传递给主界面线程
gui_log_queue = queue.Queue()

# 终端格式: 统一色彩渲染！
# 时间固定为绿色作为视觉锚点，后面的所有内容（级别、线程、模块、报文）全部被 <level> 包裹。
# 这样当发生 ERROR 时，除了时间，整行都会变成醒目的红色。
TERMINAL_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> "
    "<level>"
    "{level.name: <1.1} "
    "[{thread.id: >5}] "
    "[{name: <8.8}:{line: >3}] "
    "[{extra[module]: <6.6}] | "
    "{message}"
    "</level>"
)

# 文件持久化格式: 保留完整元数据，方便日后利用脚本进行自动化分析
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} "
    "[{level.name: <8}] "
    "[{process.id: >5}:{thread.id: >5}] "
    "[{name}:{function}:{line}] "
    "[{extra[module]: <6.6}] | "
    "{message}"
)

# ==========================================
# 2. 配置管理类 (Configuration Manager)
# ==========================================


class LogManager:
    """集中管理 Loguru 的路由拓扑、自定义级别与补丁机制"""

    @classmethod
    def setup_system(cls):
        """系统日志初始化总入口"""
        logger.remove()  # 拔掉出厂默认的 Handler

        cls._configure_levels()

        # 挂载上下文补丁
        configured_logger = logger.patch(cls._patch_record)

        # 挂载 1：全量终端输出 (开启异步 enqueue=True)
        configured_logger.add(
            sys.stdout,
            format=TERMINAL_FORMAT,
            level="DEBUG",
            colorize=True,
            enqueue=True
        )

        # 挂载 2：系统主日志文件
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        configured_logger.add(
            log_dir / "system_{time:YYYY-MM-DD}.log",
            format=FILE_FORMAT,
            level="DEBUG",
            rotation="00:00",
            retention="7 days",
            enqueue=True,
            delay=True
        )

        # 挂载 3：GUI 事件队列 Sink
        configured_logger.add(
            cls._gui_enqueue_sink,
            format=TERMINAL_FORMAT,
            level="INFO"  # GUI 通常不需要高频 DEBUG 刷屏
        )

        return configured_logger

    @staticmethod
    def _configure_levels():
        """配置和覆盖日志级别"""
        # 1. 强制给 INFO 加上青色，解决默认没有颜色的问题，让常态信息更清爽
        # logger.level("INFO", color="<cyan>")
        logger.level("INFO", color="<fg #A9DFBF>")

        # 2. 注册底层硬件/网络调试专用的自定义级别：RAW (用于输出原始十六进制流)
        # NO=15，介于 DEBUG(10) 和 INFO(20) 之间。截断后显示为 'R'
        logger.level("RAW", no=15, color="<blue>", icon="📦")

    @staticmethod
    def _patch_record(record: dict) -> None:
        """全局拦截器：确保所有的日志都有 'module' 标识，保障格式化对齐"""
        # 如果调用者没有 bind(module="xxx")，就给一个默认的 "SYS" 占位
        record["extra"].setdefault("module", "SYS   ")

    @staticmethod
    def _gui_enqueue_sink(message: "loguru.Message") -> None:
        """跨线程传递，只塞队列，不在此处渲染 UI"""
        gui_log_queue.put((str(message), message.record))


# ==========================================
# 3. 协议辅助工具
# ==========================================

def format_packet(header: bytes, cmd: int, payload: bytes, crc: bytes) -> str:
    """将拆包后的协议转化为高可读性的 Hex Dump 字符串"""
    hex_header = header.hex(' ').upper()
    hex_cmd = f"{cmd:02X}"
    hex_payload = payload.hex(' ').upper() if payload else "N/A"
    hex_crc = crc.hex(' ').upper()
    return f"HDR[{hex_header}] CMD[{hex_cmd}] DATA[{hex_payload}] CRC[{hex_crc}]"


# ==========================================
# 4. 全局导出
# ==========================================
# 整个系统只会在这里执行一次初始化
log = LogManager.setup_system()


# ==========================================
# 5. 各业务模块使用示例 (Usage Examples)
# ==========================================
if __name__ == "__main__":
    import time
    import threading

    # --- 用例 1：系统启动日志 (带青色的 INFO) ---
    log.info("Debug Client 初始化...")
    log.debug("读取项目根目录配置文件")

    # --- 用例 2：底层网络与固件 IO 模块 ---
    net_log = log.bind(module="NET")

    def simulate_network_recv():
        net_log.info("开启增量 IO 缓冲区")
        time.sleep(0.1)
        # 使用我们自定义的 RAW 级别打印纯粹的报文流
        net_log.log("RAW", "捕获原始帧 -> {}",
                    format_packet(b'\xAA\x55', 0x01, b'\x00\x11', b'\xFF\xFF'))
        net_log.warning("检测到序列号跳变，可能发生丢包")
        net_log.error("增量解析器抛出异常：越界访问")

    # --- 用例 3：算法验证模块 ---
    algo_log = log.bind(module="NV5_OC")

    def simulate_algorithm_task():
        algo_log.info("初始化 nv5 算法库验证接口")
        time.sleep(0.1)
        algo_log.debug("向嘉豪发送当前模块连调状态报告")

    # 启动线程查看纯色对齐效果
    t1 = threading.Thread(target=simulate_network_recv, name="RecvThre")
    t2 = threading.Thread(target=simulate_algorithm_task, name="AlgoThre")
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 清空队列防止退出阻塞
    while not gui_log_queue.empty():
        gui_log_queue.get_nowait()
