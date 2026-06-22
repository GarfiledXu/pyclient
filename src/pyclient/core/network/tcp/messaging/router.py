from typing import Callable, Dict, List
from ..format.packet import NvsPacket


class PacketRouter:
    """消息路由中心：维护使能开关(Filter)与被动 Pub/Sub"""

    def __init__(self):
        self._enabled_cmds: Dict[str, bool] = {}
        self._subscribers: Dict[str, List[Callable[[NvsPacket], None]]] = {}

    def set_enable(self, cmd: str, enable: bool):
        """动态配置某类报文是否允许通行"""
        self._enabled_cmds[cmd] = enable

    def is_enabled(self, cmd: str) -> bool:
        """默认通行，除非显式关闭"""
        return self._enabled_cmds.get(cmd, True)

    def subscribe(self, cmd: str, callback: Callable[[NvsPacket], None]):
        """注册被动消息监听器（如心跳上报）"""
        if cmd not in self._subscribers:
            self._subscribers[cmd] = []

        # 避免重复订阅
        if callback not in self._subscribers[cmd]:
            self._subscribers[cmd].append(callback)

    def route_passive(self, pkt: NvsPacket):
        """触发订阅回调"""
        subs = self._subscribers.get(pkt.cmd, [])
        for sub in subs:
            try:
                sub(pkt)
            except Exception:
                pass
