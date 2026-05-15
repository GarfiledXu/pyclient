import pytest
from bak.nvs_client import NVSClient
from bak.nvs_file_svc import NvsFileSvc


@pytest.fixture(scope="session")
def client():
    """全局唯一的下位机通信 Client"""
    # c = NVSClient("192.168.100.123", 9666)
    c = NVSClient("192.168.10.110", 9666)
    c.connect()

    # 初始化连接握手 (此时 SEND 级别已经在入口处注册完毕)
    c.send_cmd("Connect")
    c.wait_for_response("Connect")

    yield c

    # 整个 Session 测试结束后，安全断开
    c.disconnect()


@pytest.fixture(scope="session")
def svc(client):
    """文件传输业务服务类"""
    return NvsFileSvc(client)
