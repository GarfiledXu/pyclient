import socket
import json
import threading
import time
from queue import Queue, Empty
from dataclasses import asdict
from typing import Type, TypeVar, Any

from pyclient.logger import log
from pyclient.core.cmd_dto import BaseCmd
from pyclient.core.network.tcp.exception import NvsTimeoutError, NvsBusinessError

T_Cmd = TypeVar('T_Cmd', bound=BaseCmd)


class NVSClient:
    """网络层传输网关：处理原始 TCP 字节流与强类型 DTO 之间的状态机序列化"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self._recv_thread = None
        self._msg_queue = Queue()

    def connect(self, timeout: float = 3.0):
        """建立网络连接并启动底层异步接收状态机循环线程"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        try:
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(0.5)
            self.running = True
            self._recv_thread = threading.Thread(
                target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            log.bind(module="NET").info(
                f"成功连接至下位机服务器 -> {self.host}:{self.port}")
        except Exception as e:
            log.bind(module="NET").error(f"连接下位机失败: {e}")
            raise

    def disconnect(self):
        """关闭 socket 链路并安全回收同步线程资产"""
        self.running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except Exception:
                pass
        if self._recv_thread:
            self._recv_thread.join(timeout=1.0)
        log.bind(module="NET").info("已断开远端下位机链路连接")

    def send_cmd(self, cmd: str, payload_dict: dict = None):
        """序列化并发送文本/JSON标准控制指令包"""
        p_str = json.dumps(payload_dict or {}, separators=(",", ":"))
        msg = f"{cmd}\r" if not payload_dict else f"{cmd}-#{p_str}\r"
        log.bind(module="RAW").log("RAW", f"SEND -> {msg!r}")
        self.sock.sendall(msg.encode('utf-8'))

    def send_binary(self, cmd: str, header: dict, binary_data: bytes):
        """序列化并发送含前置 JSON 元数据的混合二进制数据包"""
        h_str = json.dumps(header, separators=(",", ":"))
        head = f"{cmd}-#{h_str}-#".encode('utf-8')
        log.bind(module="RAW").log(
            "RAW", f"SEND_BIN -> {head!r} + <Bytes: {len(binary_data)}>")
        self.sock.sendall(head + binary_data + b'\r')

    def wait_for_response(self, expected_cmd: str, timeout: float = 10.0) -> dict:
        """从消息队列中检索特定预期命令的响应，拦截全局 ER 异常"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self._msg_queue.get(timeout=0.1)
                if msg["cmd"] == expected_cmd:
                    return msg
                if msg["cmd"] == "ER" and expected_cmd.upper() in msg["raw"].upper():
                    return msg
            except Empty:
                continue
        raise NvsTimeoutError(expected_cmd, timeout)

    def request_dto(self, cmd_class: Type[T_Cmd], max_retries: int = 3, retry_delay: float = 0.1, **kwargs) -> Any:
        """强类型命令调度引擎：处理业务请求、解析响应、支持对 NVS_ERR_BUSY(04) 自动重试"""
        cmd_name = cmd_class.CMD_NAME
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                try:
                    req_obj = cmd_class.Req(**kwargs)
                except TypeError as e:
                    raise ValueError(f"装配 {cmd_name} 参数失败: {e}")

                req_dict = asdict(req_obj)
                binary_out = req_dict.pop('binary_data', None)

                if binary_out is not None and len(binary_out) > 0:
                    self.send_binary(cmd_name, req_dict, binary_out)
                else:
                    self.send_cmd(cmd_name, req_dict)

                raw_res = self.wait_for_response(cmd_name)

                if raw_res['cmd'] == "ER":
                    payload = raw_res.get('payload', '')
                    error = NvsBusinessError(cmd_name, payload)

                    if error.error_code == "04" and attempt < max_retries:
                        log.bind(module="NET").warning(
                            f"下位机原子锁忙 (04)，[{cmd_name}] 启动第 {attempt + 1} 次重试...")
                        time.sleep(retry_delay)
                        continue
                    raise error

                res_dict = {}
                payload = raw_res.get('payload', '')

                if payload:
                    if payload.strip() == "OK":
                        pass
                    else:
                        try:
                            res_dict = json.loads(payload)
                        except json.JSONDecodeError:
                            res_dict = {}

                if raw_res.get('binary'):
                    res_dict['binary_data'] = raw_res['binary']

                valid_keys = cmd_class.Res.__dataclass_fields__.keys()
                filtered_dict = {k: v for k,
                                 v in res_dict.items() if k in valid_keys}
                return cmd_class.Res(**filtered_dict)

            except (NvsTimeoutError, NvsBusinessError) as e:
                last_exception = e
                if attempt >= max_retries:
                    raise last_exception

    def _recv_loop(self):
        """流式字节接收状态机核心接收循环"""
        buffer = bytearray()
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    break
                buffer.extend(data)

                while True:
                    first_sep = buffer.find(b'-#')
                    if first_sep == -1:
                        pos = buffer.find(b'\r')
                        if pos != -1:
                            self._process_msg(buffer[:pos + 1])
                            buffer = buffer[pos + 1:]
                            continue
                        break

                    cmd_part = buffer[:first_sep]
                    # 识别是否为带有特殊二进制块的数据读取指令
                    if b"File_SVC_Read_Data" in cmd_part:
                        second_sep = buffer.find(b'-#', first_sep + 2)
                        if second_sep == -1:
                            break
                        try:
                            json_bytes = buffer[first_sep + 2: second_sep]
                            meta = json.loads(json_bytes.decode('utf-8'))
                            data_len = meta.get('data_len', 0)
                            total_expected_len = second_sep + 2 + data_len + 1

                            if len(buffer) < total_expected_len:
                                break

                            exact_binary = buffer[second_sep +
                                                  2: second_sep + 2 + data_len]
                            self._msg_queue.put({
                                "cmd": cmd_part.decode('utf-8', errors='ignore'),
                                "payload": json_bytes.decode('utf-8'),
                                "binary": exact_binary,
                                "raw": buffer[:total_expected_len].decode('utf-8', errors='ignore')
                            })
                            buffer = buffer[total_expected_len:]
                            continue
                        except Exception:
                            break
                    else:
                        pos = buffer.find(b'\r')
                        if pos == -1:
                            break
                        self._process_msg(buffer[:pos + 1])
                        buffer = buffer[pos + 1:]
                        continue
            except socket.timeout:
                continue
            except Exception:
                break

    def _process_msg(self, raw_bytes: bytes):
        """将不含原始大二进制块的普通控制包解包注入内部队列"""
        msg = raw_bytes.rstrip(b'\r')
        log.bind(module="RAW").log("RAW", f"RECV <- {msg!r}")

        raw_str = msg.decode('utf-8', errors='ignore')
        if msg.startswith(b"ER-#"):
            self._msg_queue.put(
                {"cmd": "ER", "payload": raw_str, "raw": raw_str})
            return

        parts = msg.split(b"-#", 2)
        cmd = parts[0].decode('utf-8', errors='ignore')
        payload = parts[1].decode(
            'utf-8', errors='ignore') if len(parts) >= 2 else ""
        binary = parts[2] if len(parts) == 3 else b''

        self._msg_queue.put({
            "cmd": cmd,
            "payload": payload,
            "binary": binary,
            "raw": raw_str
        })
