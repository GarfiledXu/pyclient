from pyclient.logger import log
from pyclient.config import cfg, ConfigManager
import time
import sys
from pathlib import Path

# 将 src/ 目录动态注入系统路径，支持开发环境直接运行
root_path = Path(__file__).resolve().parents[1]
src_path = root_path / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def format_packet(header: bytes, cmd: int, payload: bytes, crc: bytes) -> str:
    """将通信报文字节流转换为十六进制可视化字符串"""
    h_str = header.hex(' ').upper()
    p_str = payload.hex(' ').upper() if payload else "N/A"
    c_str = crc.hex(' ').upper()
    return f"HDR[{h_str}] CMD[{cmd:02X}] DATA[{p_str}] CRC[{c_str}]"


def run_test():
    root_dir = ConfigManager.get_root_dir()
    user_config_path = root_dir / "config" / "config.toml"

    print(f"\n[测试环境信息]")
    print(f"项目根目录: {root_dir}")
    print(f"用户配置文件: {user_config_path}")
    print(f"当前日志落盘物理路径: {root_dir / cfg.log.file.path}\n")

    # 1. 常规系统日志测试
    sys_log = log.bind(module="SYS")
    sys_log.info("系统初始化完成，全局静态配置固化成功。")
    sys_log.debug("Debug 级别日志输出测试。")

    time.sleep(0.3)

    # 2. 跨模块业务日志测试
    net_log = log.bind(module="NET")
    net_log.warning("网络模块心跳延迟波动测试。")

    # 3. RAW 级别特定格式覆盖测试
    print("\n[开始推送纯净 RAW 报文流]")
    for i in range(3):
        packet = format_packet(b'\xAA\x55', i, b'\x02\x04', b'\x0D\x0A')
        net_log.log("RAW", "RECV <- {}", packet)
        time.sleep(0.1)

    print("")
    sys_log.info("测试脚本执行结束。")


if __name__ == "__main__":
    run_test()
