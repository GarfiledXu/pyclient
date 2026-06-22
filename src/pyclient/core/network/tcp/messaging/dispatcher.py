import json
import time
from concurrent.futures import Future
from typing import Dict, Any, Type, TypeVar
from dataclasses import asdict
from ..format.packet import NvsPacket
from ..business.cmd_dto import BaseCmd
from .......bak.exception import NvsTimeoutError, NvsBusinessError, NvsNetworkDroppedError

T_Cmd = TypeVar('T_Cmd', bound=BaseCmd)


class CommandDispatcher:
    def __init__(self, send_func):
        self._send_func = send_func
        self._pending_requests: Dict[str, Future] = {}

    def abort_all(self, reason: Exception):
        """【熔断机制】当网络断开时，强制终止所有正在等待回包的 Future"""
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(reason)
        self._pending_requests.clear()

    # ... (原有 _pack_request 保持不变)

    def request_sync(self, cmd_class: Type[T_Cmd], timeout: float = 10.0, max_retries: int = 3, **kwargs) -> Any:
        cmd_name = cmd_class.CMD_NAME
        last_err = None

        for attempt in range(max_retries + 1):
            req_obj = cmd_class.Req(**kwargs)
            raw_bytes = self._pack_request(cmd_name, asdict(req_obj))

            future = Future()
            self._pending_requests[cmd_name] = future

            # 发送失败直接抛出网络异常，不浪费时间
            if not self._send_func(raw_bytes):
                self._pending_requests.pop(cmd_name, None)
                raise NvsNetworkDroppedError()

            try:
                pkt: NvsPacket = future.result(timeout=timeout)
                # ... (原有的 ER 处理与 04 重试逻辑保持不变)

            except TimeoutError:
                raise NvsTimeoutError(cmd_name, timeout)
            except Exception as e:
                # 这里的 Exception 就能捕获到 abort_all 塞入的 NvsNetworkDroppedError
                last_err = e
                if attempt >= max_retries:
                    raise last_err
            finally:
                self._pending_requests.pop(cmd_name, None)

    def handle_incoming(self, pkt: NvsPacket) -> bool:
        """核心匹配逻辑：判断该包是否为主动请求的回包"""
        # 如果是报错，尝试根据 payload 提取出引发报错的 cmd
        target_cmd = pkt.cmd
        if pkt.is_error:
            parts = pkt.payload_str.split("-#")
            if len(parts) >= 2:
                target_cmd = parts[1]

        future = self._pending_requests.get(target_cmd)
        if future and not future.done():
            future.set_result(pkt)
            return True
        return False

    # ... (原有 handle_incoming 保持不变)
