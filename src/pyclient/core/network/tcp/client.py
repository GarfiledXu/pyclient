from .link.connection import TcpConnection
from .format.framer import StreamFramer
from .format.packet import NvsPacket
from .messaging.router import PacketRouter
from .messaging.dispatcher import CommandDispatcher
from .business.file_transfer import FileTransferService
from ......bak.exception import NvsNetworkDroppedError


class TcpProtocolClient:
    def __init__(self, host: str, port: int):
        self.router = PacketRouter()
        self.dispatcher = CommandDispatcher(send_func=self._raw_send)
        self.framer = StreamFramer(on_packet_parsed=self._on_packet_parsed)

        # 🌟 核心：将连接状态的钩子与熔断器绑定
        self.connection = TcpConnection(
            host=host,
            port=port,
            on_data_received=self.framer.feed,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected
        )

        self.file = FileTransferService(self.dispatcher)

    def connect(self):
        self.connection.connect()

    def disconnect(self):
        self.connection.disconnect()

    def _raw_send(self, data: bytes) -> bool:
        return self.connection.send(data)

    def _on_connected(self):
        """恢复连接时，可以重置某些业务状态"""
        pass

    def _on_disconnected(self):
        """断联瞬间：一剑封喉，熔断所有正在等结果的业务请求"""
        self.dispatcher.abort_all(NvsNetworkDroppedError())

    def _on_packet_parsed(self, pkt: NvsPacket):
        if not self.router.is_enabled(pkt.cmd):
            return
        handled = self.dispatcher.handle_incoming(pkt)
        if not handled:
            self.router.route_passive(pkt)
