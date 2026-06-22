import socket
import threading
import time
from typing import Callable
from pyclient.logger import log


class TcpConnection:
    """工业级物理链路层：带自动重连守护与系统级 Keep-Alive"""

    def __init__(
        self,
        host: str,
        port: int,
        on_data_received: Callable[[bytes], None],
        on_connected: Callable[[], None],
        on_disconnected: Callable[[], None]
    ):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False

        self._supervisor_thread = None
        self.reconnect_interval = 3.0  # 失败重试间隔

        # 回调挂载点
        self._on_data_received = on_data_received
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

    def connect(self):
        """启动守护线程，引擎点火"""
        if self.running:
            return
        self.running = True
        self._supervisor_thread = threading.Thread(
            target=self._supervise_loop, daemon=True)
        self._supervisor_thread.start()

    def disconnect(self):
        """彻底关闭引擎，停止重连"""
        self.running = False
        self._close_socket()
        if self._supervisor_thread:
            self._supervisor_thread.join(timeout=2.0)

    def send(self, data: bytes) -> bool:
        """安全发送，若断联则直接丢弃并返回 False"""
        if not self.sock:
            return False
        try:
            self.sock.sendall(data)
            return True
        except Exception:
            return False

    def _close_socket(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _supervise_loop(self):
        """核心守护循环：永远试图保持连接，直到 running 被设为 False"""
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)  # 连接超时
                self.sock.connect((self.host, self.port))

                # 开启 TCP 底层 Keep-Alive (定时检查)，防半开连接假死
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.sock.settimeout(0.5)  # 恢复读取超时，避免阻塞中断

                log.bind(module="NET").success(
                    f"链路已连接 -> {self.host}:{self.port}")
                self._on_connected()

                # 进入阻塞接收状态机，直到发生断联异常才会退出
                self._recv_loop()

            except Exception as e:
                # 屏蔽无意义的错误刷屏，仅在连接失败时提示
                if self.running:
                    log.bind(module="NET").warning(
                        f"连接失败或中断，{self.reconnect_interval}秒后重试... ({e})")
            finally:
                self._close_socket()
                self._on_disconnected()  # 触发上层熔断

                if self.running:
                    time.sleep(self.reconnect_interval)

    def _recv_loop(self):
        """仅负责读数据，抛出任何异常即代表当前 Socket 死亡"""
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    break  # 收到空包，远端正常关闭(FIN)
                self._on_data_received(data)
            except socket.timeout:
                continue  # 正常超时，继续轮询
            except Exception:
                break  # 物理报错 (如 ECONNRESET)，打断接收，交由外层重连
