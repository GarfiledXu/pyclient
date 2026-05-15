from pyclient.config import cfg, ConfigLoader
from pyclient.logger import log
import time
import sys
from pathlib import Path

# ==========================================
# 0. 核心：确保能找到 src 下的包
# ==========================================
# 这一步是为了让你在 demo 目录下直接运行脚本时，能 import 到 pyclient
root_path = Path(__file__).resolve().parents[1]
src_path = root_path / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# ==========================================
# 1. 对齐后的导入
# ==========================================
# 注意：现在是从 pyclient 顶级包导入
# 如果你把 format_packet 留在了 logger.py 或者是挪到了 util，按实际位置导入
# 这里假设你把它挪到了 pyclient.util.conv (符合强迫症的分类)
# from pyclient.util.conv import format_packet


def format_packet(header: bytes, cmd: int, payload: bytes, crc: bytes) -> str:
    """(临时保留在测试脚本中或按实际位置导入)"""
    h_str = header.hex(' ').upper()
    p_str = payload.hex(' ').upper() if payload else "N/A"
    c_str = crc.hex(' ').upper()
    return f"HDR[{h_str}] CMD[{cmd:02X}] DATA[{p_str}] CRC[{c_str}]"


def run_test():
    # 获取对齐后的路径信息
    root_dir = ConfigLoader.get_root_dir()
    user_config_path = root_dir / "config" / "config.toml"

    print(f"\n[测试环境信息 - 对齐版]")
    print(f"项目根目录: {root_dir}")
    print(f"用户配置文件: {user_config_path}")
    print(f"配置文件是否存在: {user_config_path.exists()}\n")

    # 1. 常规日志打印
    sys_log = log.bind(module="SYS")
    sys_log.info("系统初始化完成，配置已通过 pyclient.config 加载。")
    sys_log.debug("这是一条 Debug 日志，测试增量配置是否生效。")

    time.sleep(0.5)

    # 2. 网络模块日志
    net_log = log.bind(module="NET")
    net_log.warning("检测到下位机心跳延迟...")

    # 3. 验证 RAW 级别覆盖特性
    print("\n[开始推送纯净 RAW 数据流]")
    for i in range(3):
        packet = format_packet(b'\xAA\x55', i, b'\x01\x02', b'\xFF\xFF')
        # 此时会触发 logger.py 中对应的 RAW 级别格式化规则
        net_log.log("RAW", "RECV <- {}", packet)
        time.sleep(0.2)

    sys_log.info("测试结束。")


if __name__ == "__main__":
    run_test()
