import os
import zlib
import hashlib
from typing import Callable, Optional

import pyclient.core.cmd_dto as dto
from pyclient.core.protocol import NVSClient
from pyclient.core.network.tcp.exception import NvsFileIOError


class NvsFileSvc:
    """文件子系统业务层路由服务控制器 (对齐下位机 File_SVC 模块行为)"""

    def __init__(self, client: NVSClient):
        self.client = client

    @staticmethod
    def calculate_md5(file_path: str) -> str:
        """计算本地文件的 MD5 摘要值"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def write(self, local_path: str, remote_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """将本地文件通过流式强类型对象分块协议安全写入下位机，内建 MD5 闭环校验"""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"本地源文件不存在: {local_path}")

        file_size = os.path.getsize(local_path)
        local_md5 = self.calculate_md5(local_path)

        open_res = self.client.request_dto(
            dto.CmdWriteOpen,
            path=remote_path,
            total_size=file_size,
            md5=local_md5
        )
        sid = open_res.session_id
        step = 4096
        offset = 0

        try:
            with open(local_path, 'rb') as f:
                while offset < file_size:
                    chunk = f.read(step)
                    if not chunk:
                        break

                    self.client.request_dto(
                        dto.CmdWriteData,
                        session_id=sid,
                        offset=offset,
                        data_len=len(chunk),
                        crc32=zlib.crc32(chunk) & 0xFFFFFFFF,
                        binary_data=chunk
                    )
                    offset += len(chunk)
                    if progress_callback:
                        progress_callback(offset, file_size)

            self.client.request_dto(dto.CmdClose, session_id=sid)

        except Exception as e:
            try:
                self.client.request_dto(dto.CmdClose, session_id=sid)
                self.client.request_dto(dto.CmdDelete, path=remote_path)
            except Exception:
                pass
            raise NvsFileIOError(f"文件写入异常中断: {e}")

        stat_res = self.client.request_dto(dto.CmdStat, path=remote_path)
        if stat_res.md5 != local_md5:
            self.client.request_dto(dto.CmdDelete, path=remote_path)
            raise NvsFileIOError(f"完整性校验失败: 期望={local_md5}, 实际={stat_res.md5}")

        return True

    def read(self, remote_path: str, local_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """从下位机读取目标文件并落盘至本地，内建单包分块 CRC32 数据校验"""
        open_res = self.client.request_dto(dto.CmdReadOpen, path=remote_path)
        sid = open_res.session_id
        total_size = open_res.file_size
        offset = 0

        try:
            with open(local_path, 'wb') as f:
                while offset < total_size:
                    data_res = self.client.request_dto(
                        dto.CmdReadData,
                        session_id=sid,
                        offset=offset,
                        size=8192
                    )

                    chunk = data_res.binary_data
                    remote_crc32 = data_res.crc32
                    local_crc32 = zlib.crc32(chunk) & 0xFFFFFFFF

                    if remote_crc32 != 0 and local_crc32 != remote_crc32:
                        raise NvsFileIOError(f"分包 CRC32 校验失败，偏移量: {offset}")

                    f.write(chunk)
                    offset += len(chunk)
                    if progress_callback:
                        progress_callback(offset, total_size)

            self.client.request_dto(dto.CmdClose, session_id=sid)

        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            try:
                self.client.request_dto(dto.CmdClose, session_id=sid)
            except Exception:
                pass
            raise NvsFileIOError(f"文件读取异常中断: {e}")

        return True
