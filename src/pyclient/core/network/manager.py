from .tcp.client import TcpProtocolClient


class NetworkManager:
    """全系统网络层唯一出入口"""

    def __init__(self, host: str, port: int):
        # 挂载 TCP 协议族门面
        self.tcp = TcpProtocolClient(host, port)
        # 未来扩展:
        # self.udp = UdpProtocolClient(...)

    def __enter__(self):
        self.tcp.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tcp.disconnect()
