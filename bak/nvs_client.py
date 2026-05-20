import socket
import json
import threading
import time
from queue import Queue, Empty
from loguru import logger
from dataclasses import asdict
from typing import Type, TypeVar, Any

# 引入我们刚刚定义好的 DTO 基类
from bak.nvs_cmd_dto import BaseCmd

# 泛型约束，用于让 IDE 完美推导 request_dto 返回的 Res 类型
T_Cmd = TypeVar('T_Cmd', bound=BaseCmd)


# ==========================================
# 1. 异常体系定义
# ==========================================
class NvsProtocolError(Exception):
    """协议基类异常"""
    pass


class NvsTimeoutError(NvsProtocolError):
    """通信层错误：对方没响应 (链路问题)"""

    def __init__(self, cmd, timeout):
        self.cmd = cmd
        self.timeout = timeout
        super().__init__(f"通信超时: 指令 [{cmd}] 在 {timeout}s 内未响应，请检查链路或设备状态")


class NvsBusinessError(NvsProtocolError):
    """业务层错误：对方回了 ER (逻辑问题)"""

    # 错误码映射表（占位，后续可扩展）
    ERROR_MAP = {
        "101": "FILE_NOT_FOUND",
        "102": "ACCESS_DENIED",
        "103": "DISK_FULL",
        # 可以在这里继续添加...
    }

    def __init__(self, cmd, raw_payload):
        self.cmd = cmd  # 发起请求的命令名，如 CmdStat
        self.raw_payload = raw_payload  # 原始载荷: "ER-#File_SVC_STAT-#101"

        # 默认值
        self.module = "Unknown"
        self.error_code = "-1"
        self.error_desc = "Unknown Error"

        # --- 精准提取逻辑 ---
        # 如果格式是 ER-#Module-#Code
        parts = raw_payload.split("-#")

        if len(parts) >= 3:
            # parts[0] 是 'ER'，跳过
            self.module = parts[1]     # 'File_SVC_STAT'
            self.error_code = parts[2]   # '101'
        elif len(parts) == 2:
            # 兼容处理可能是 Module-#Code 的情况
            self.module = parts[0]
            self.error_code = parts[1]

        # 映射错误描述
        self.error_desc = self.ERROR_MAP.get(
            self.error_code, f"CODE_{self.error_code}")

        super().__init__(
            f"业务报错: 命令[{self.cmd}] -> 模块[{self.module}] 返回错误码[{self.error_code}] ({self.error_desc})"
        )


class NVSClient:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sock, self.running = None, False
        self._recv_thread = None
        self._msg_queue = Queue()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(3.0)
        try:
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(0.5)
            self.running = True
            self._recv_thread = threading.Thread(
                target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            logger.success(f"Connected to {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Connect failed: {e}")
            raise

    def disconnect(self):
        self.running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except:
                pass
        if self._recv_thread:
            self._recv_thread.join(timeout=1.0)
        logger.warning("Disconnected")

    def _recv_loop(self):
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
                                "binary": exact_binary
                            })
                            buffer = buffer[total_expected_len:]
                            continue
                        except:
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
            except:
                break

    def _process_msg(self, raw_bytes: bytes):
        msg = raw_bytes.rstrip(b'\r')
        display = f"{msg[:120]!r}... <Total:{len(raw_bytes)}B>" if len(
            msg) > 200 else f"{msg!r}"
        logger.log("RECV", display)
        if msg.startswith(b"ER-#"):
            self._msg_queue.put({"cmd": "ER", "payload": msg.decode(
                'utf-8'), "raw": msg.decode('utf-8')})
            return
        parts = msg.split(b"-#", 2)
        cmd = parts[0].decode('utf-8')
        payload = parts[1].decode('utf-8') if len(parts) >= 2 else ""
        binary = parts[2] if len(parts) == 3 else b''
        self._msg_queue.put({"cmd": cmd, "payload": payload,
                             "binary": binary, "raw": msg.decode('utf-8')})

    def send_cmd(self, cmd: str, payload_dict: dict = None):
        """[底层接口] 兼容旧模式：发送纯字符串/字典组合"""
        p_str = json.dumps(payload_dict or {}, separators=(",", ":"))
        msg = f"{cmd}\r" if not payload_dict else f"{cmd}-#{p_str}\r"
        logger.log("SEND", f"{msg!r}")
        self.sock.sendall(msg.encode('utf-8'))

    def send_binary(self, cmd: str, header: dict, binary_data: bytes):
        """[底层接口] 兼容旧模式：发送纯字符串/字典/二进制组合"""
        h_str = json.dumps(header, separators=(",", ":"))
        head = f"{cmd}-#{h_str}-#".encode('utf-8')
        logger.log("SEND_BIN", f"{head!r} <Binary Data: {len(binary_data)}B>")
        self.sock.sendall(head + binary_data + b'\r')

    def wait_for_response(self, expected_cmd: str, timeout: float = 10.0) -> dict:
        """[底层接口] 阻塞等待指定指令的原始字典回复"""
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
        raise TimeoutError(f"Wait for '{expected_cmd}' timeout")

    # =================================================================
    # 🌟 优化后的调度引擎：支持 Busy 自动重试与结构化解析
    # =================================================================
    def request_dto(self, cmd_class: Type[T_Cmd], max_retries=3, retry_delay=0.1, **kwargs) -> Any:
        """
        强类型指令执行器：
        - 传入 DTO 类及参数，自动封装发送并阻塞等待。
        - 针对下位机返回的 NVS_ERR_BUSY (04) 错误码具备自动重试机制。
        """
        cmd_name = cmd_class.CMD_NAME
        last_exception = None

        # 1. 重试循环逻辑
        for attempt in range(max_retries + 1):
            try:
                # --- 阶段 A: 装配与发送 ---
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

                # --- 阶段 B: 等待响应 ---
                try:
                    raw_res = self.wait_for_response(cmd_name)
                except Exception as e:
                    # 发生底层通信超时
                    raise NvsTimeoutError(cmd_name, 5.0)

                # --- 阶段 C: 业务错误分析 (含 BUSY 重试) ---
                if raw_res['cmd'] == "ER":
                    payload = raw_res.get('payload', '')
                    error = NvsBusinessError(cmd_name, payload)

                    # 🚀 核心逻辑：如果下位机正忙 (04)，且未达到重试上限，则等待后重试
                    if error.error_code == "04" and attempt < max_retries:
                        logger.warning(
                            f"下位机原子锁忙 (04)，指令 [{cmd_name}] 正在进行第 {attempt + 1} 次重试...")
                        time.sleep(retry_delay)
                        continue  # 跳转到下一轮循环进行发送

                    raise error  # 真正的业务错误或重试耗尽，抛出异常

                # --- 阶段 D: 响应负载解析 ---
                res_dict = {}
                payload = raw_res.get('payload', '')

                if payload:
                    # 识别简单报文 (OK)
                    if payload.strip() == "OK":
                        logger.debug(f"指令 [{cmd_name}] 接收到简单报文 (无 JSON 载荷)")
                    else:
                        try:
                            res_dict = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.warning(
                                f"指令 [{cmd_name}] 载荷为非 JSON 简单报文: {payload}")
                else:
                    logger.debug(f"指令 [{cmd_name}] 响应结束，无数据载荷")

                # 注入二进制回包
                if raw_res.get('binary'):
                    res_dict['binary_data'] = raw_res['binary']

                # --- 阶段 E: 实例化响应对象 ---
                # 过滤掉非 DTO 定义的冗余字段
                valid_keys = cmd_class.Res.__dataclass_fields__.keys()
                filtered_dict = {k: v for k,
                                 v in res_dict.items() if k in valid_keys}

                return cmd_class.Res(**filtered_dict)

            except (NvsTimeoutError, NvsBusinessError) as e:
                # 记录最后一次异常，如果循环结束仍未成功则抛出
                last_exception = e
                if attempt >= max_retries:
                    raise last_exception
    # =================================================================
    # 🌟 新增的高阶调度引擎：对象化通信接口
    # =================================================================
    # def request_dto(self, cmd_class: Type[T_Cmd], **kwargs) -> Any:
    #     """
    #     强类型指令执行器：传入 DTO 类及参数，自动封装、发送并阻塞等待，最终返回 DTO 响应对象。
    #     """
    #     cmd_name = cmd_class.CMD_NAME

    #     # 1. 实例化强类型请求对象并转为字典
    #     try:
    #         req_obj = cmd_class.Req(**kwargs)
    #     except TypeError as e:
    #         raise ValueError(f"装配 {cmd_name} 参数失败: {e}")

    #     req_dict = asdict(req_obj)

    #     # 2. 智能拦截并剥离特殊二进制载荷 (防止 json.dumps 崩溃)
    #     binary_out = req_dict.pop('binary_data', None)

    #     # 3. 智能路由到对应底层方法
    #     if binary_out is not None and len(binary_out) > 0:
    #         self.send_binary(cmd_name, req_dict, binary_out)
    #     else:
    #         self.send_cmd(cmd_name, req_dict)

    #     # # 4. 阻塞等待远端回包
    #     # raw_res = self.wait_for_response(cmd_name)

    #     # # 5. 全局错误拦截
    #     # if raw_res['cmd'] == "ER":
    #     #     raise RuntimeError(f"远端异常 ({cmd_name}): {raw_res.get('payload')}")
    #     # 4. 阻塞等待远端回包
    #     try:
    #         raw_res = self.wait_for_response(cmd_name)
    #     except Exception as e:
    #         # 这里的 Exception 捕获视你 wait_for_response 内部抛出的类型而定
    #         # 统一封装成通信异常
    #         raise NvsTimeoutError(cmd_name, 5.0)  # 假设超时是5秒

    #     # 5. 全局业务错误拦截
    #     if raw_res['cmd'] == "ER":
    #         # 🌟 关键点：不再抛出通用的 RuntimeError，而是抛出业务异常
    #         raise NvsBusinessError(cmd_name, raw_res.get('payload', ''))

    #     # # 6. 反序列化响应 JSON
    #     # res_dict = {}
    #     # if raw_res.get('payload'):
    #     #     try:
    #     #         res_dict = json.loads(raw_res['payload'])
    #     #     except json.JSONDecodeError:
    #     #         logger.warning(f"JSON 解析失败: {raw_res['payload']}")
    #     # 6. 反序列化响应负载
    #     res_dict = {}
    #     payload = raw_res.get('payload', '')

    #     if payload:
    #         # --- 识别简单报文格式 ---
    #         if payload.strip() == "OK":
    #             # 这种情况不再视作错误，而是正常的简单响应
    #             logger.debug(f"指令 [{cmd_name}] 接收到简单报文 (无 JSON 载荷)")
    #             res_dict = {}
    #         else:
    #             try:
    #                 res_dict = json.loads(payload)
    #             except json.JSONDecodeError:
    #                 # 只有当它既不是 OK，也不是合法 JSON 时，才认为是格式存疑
    #                 logger.warning(
    #                     f"指令 [{cmd_name}] 载荷为非 JSON 简单报文: {payload}")
    #                 res_dict = {}
    #     else:
    #         # 完全没有 payload 的情况
    #         logger.debug(f"指令 [{cmd_name}] 响应结束，无数据载荷")

    #     # 7. 拼接返回的二进制数据
    #     if raw_res.get('binary'):
    #         res_dict['binary_data'] = raw_res['binary']

    #     # 8. 数据清洗：过滤掉 MCU 乱发的非预期字段，安全实例化 Res
    #     valid_keys = cmd_class.Res.__dataclass_fields__.keys()
    #     filtered_dict = {k: v for k, v in res_dict.items() if k in valid_keys}

    #     return cmd_class.Res(**filtered_dict)
