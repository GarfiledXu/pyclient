import os
import sys
from loguru import logger


def init_test_logger():
    """初始化测试框架的全局日志与环境配置"""
    # 1. 强制开启环境颜色支持
    os.environ["COLORTERM"] = "truecolor"
    os.environ["FORCE_COLOR"] = "1"

    # 2. 重置日志配置
    logger.remove()

    # 3. 注册自定义通信级别 (添加了 SEND_BIN)
    custom_levels = [
        ("SEND", 21, "<green><bold>"),
        ("RECV", 22, "<cyan><bold>"),
        ("SEND_BIN", 23, "<magenta><bold>")  # 🚀 新增：专门用于二进制大数据传输
    ]

    for name, no, color in custom_levels:
        try:
            # no 代表优先级，数值越大越容易在过滤中显示
            logger.level(name, no=no, color=color)
        except ValueError:
            # 如果级别已存在（比如多次调用 init），则跳过
            pass

    # 4. 配置控制台输出格式
    logger.add(
        sys.stdout,
        # {level: <8} 留出 8 个字符宽度，对齐 SEND_BIN 的长度
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {message}",
        level=10,
        colorize=True
    )
