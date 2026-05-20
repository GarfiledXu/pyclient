class NvsProtocolError(Exception):
    """NVS 通信协议基类异常"""
    pass


class NvsTimeoutError(NvsProtocolError):
    """网络通信超时异常：远端在指定时间内未返回任何有效报文"""
    def __init__(self, cmd: str, timeout: float):
        self.cmd = cmd
        self.timeout = timeout
        super().__init__(f"通信超时: 指令 [{cmd}] 在 {timeout}s 内未响应")


class NvsBusinessError(NvsProtocolError):
    """下位机业务层错误异常：远端返回 ER 错误报文"""
    ERROR_MAP = {
        "01": "INVALID_CMD",
        "02": "INVALID_PARAM",
        "03": "AUTH_FAILED",
        "04": "NVS_ERR_BUSY",
        "101": "FILE_NOT_FOUND",
        "102": "ACCESS_DENIED",
        "103": "DISK_FULL",
        "104": "CRC32_MISMATCH",
        "105": "MD5_MISMATCH"
    }

    def __init__(self, cmd: str, raw_payload: str):
        self.cmd = cmd
        self.raw_payload = raw_payload
        self.module = "Unknown"
        self.error_code = "-1"
        self.error_desc = "Unknown Error"

        parts = raw_payload.split("-#")
        if len(parts) >= 3:
            self.module = parts[1]
            self.error_code = parts[2]
        elif len(parts) == 2:
            self.module = parts[0]
            self.error_code = parts[1]

        self.error_desc = self.ERROR_MAP.get(self.error_code, f"CODE_{self.error_code}")
        super().__init__(
            f"业务报错: 命令[{self.cmd}] -> 模块[{self.module}] 返回错误码[{self.error_code}] ({self.error_desc})"
        )


class NvsFileIOError(NvsProtocolError):
    """文件传输业务流异常"""
    pass