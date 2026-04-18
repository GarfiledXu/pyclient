from util.log_conf import init_test_logger
import pytest
from pathlib import Path

# 1. 第一时间启动全局基建 (保证后续所有模块加载时日志已经 ready)
init_test_logger()

# 2. 使用 pytest_plugins 魔法，自动加载指定目录下的夹具
pytest_plugins = [
    "fixture.nvs_fixtures",
    # 未来可以随时无痛追加:
    # "fixtures.ble_fixtures",
    # "fixtures.pwr_fixtures",
]


# 把注册 ini 和注册命令行的代码，全放在这一个官方标准的函数里
def pytest_addoption(parser):
    # 1. 注册 ini 变量
    parser.addini("vault_folder_name", "Directory name for backup vaults")

    # 2. 注册命令行参数
    parser.addoption("--action", action="store", default="check")
    parser.addoption("--vault", action="store", default="default_gold_vault")
    parser.addoption("--vault-root", action="store", default=None)


@pytest.fixture
def run_config(request):
    cli_root = request.config.getoption("--vault-root")

    if cli_root:
        vault_root_path = Path(cli_root)
    else:
        project_root = request.config.rootpath
        folder_name = request.config.getini(
            "vault_folder_name") or "nvs_test_vaults"
        vault_root_path = project_root / folder_name

    return {
        "action": request.config.getoption("--action"),
        "vault": request.config.getoption("--vault"),
        "vault_root": vault_root_path
    }
