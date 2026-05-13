import time

from src.util.logger import log, format_packet, CONFIG_FILE, APP_DIR


def run_test():
    print(f"\n[测试环境信息]")
    print(f"程序根目录判定: {APP_DIR}")
    print(f"配置文件路径: {CONFIG_FILE}")
    print(f"配置文件是否存在: {CONFIG_FILE.exists()}\n")

    # 1. 常规日志打印 (包含完整的线程、位置、模块等元数据)
    sys_log = log.bind(module="SYS")
    sys_log.info("系统初始化完成，配置文件已加载。")
    sys_log.debug("这是一条 Debug 级别日志，应该被记录在文件中。")

    time.sleep(0.5)

    # 2. 网络模块日志
    net_log = log.bind(module="NET")
    net_log.warning("检测到下位机心跳延迟...")

    # 3. 验证 Level 覆盖特性 (RAW 级别)
    # 因为我们在 TOML 里配置了 [log.levels.RAW] show_time=false, show_details=false
    # 所以这条日志不会带有时间戳和元数据，只输出纯净内容
    print("\n[开始推送纯净 RAW 数据流]")
    for i in range(3):
        packet = format_packet(b'\xAA\x55', i, b'\x01\x02', b'\xFF\xFF')
        net_log.log("RAW", "RECV <- {}", packet)
        time.sleep(0.2)

    sys_log.info("测试结束，请查看控制台输出以及 logs 目录下的文件内容。")


if __name__ == "__main__":
    run_test()
