import os
import zlib
import hashlib
from typing import Callable, Optional

from . import cmd_dto as dto
from .......bak.exception import NvsFileIOError
from ..messaging.dispatcher import CommandDispatcher


class FileTransfer:
    """高阶业务流：文件分块可靠传输引擎"""

    def __init__(self, dispatcher: CommandDispatcher):
        # 依赖注入 L3 调度器，业务层不直接触碰底层 Client 或 Connection
        self.dispatcher = dispatcher

    @staticmethod
    def calculate_md5(file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def write(self, local_path: str, remote_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """流式分块写入下位机（内建 MD5 闭环校验与网络崩溃自动清理）"""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"本地源文件不存在: {local_path}")

        file_size = os.path.getsize(local_path)
        local_md5 = self.calculate_md5(local_path)

        # 1. 开启写会话 (使用 request_sync 发起阻塞调用)
        open_res = self.dispatcher.request_sync(
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

                    # 2. 流式发送分块
                    self.dispatcher.request_sync(
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

            # 3. 正常闭合会话
            self.dispatcher.request_sync(dto.CmdClose, session_id=sid)

        except Exception as e:
            # 异常发生（如网线拔出引发的 NvsNetworkDroppedError）
            # 尝试发送清理指令，但由于网络可能已断开，必须屏蔽这里的附加错误
            try:
                self.dispatcher.request_sync(
                    dto.CmdClose, session_id=sid, timeout=1.0)
                self.dispatcher.request_sync(
                    dto.CmdDelete, path=remote_path, timeout=1.0)
            except Exception:
                pass
            raise NvsFileIOError(f"文件流式写入异常中断: {str(e)}") from e

        # 4. 远端落盘闭环 MD5 校验
        stat_res = self.dispatcher.request_sync(dto.CmdStat, path=remote_path)
        if stat_res.md5 != local_md5:
            # 校验失败进行脏数据销毁
            try:
                self.dispatcher.request_sync(dto.CmdDelete, path=remote_path)
            except Exception:
                pass
            raise NvsFileIOError(f"完整性校验失败: 期望={local_md5}, 实际={stat_res.md5}")

        return True

    def read(self, remote_path: str, local_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """流式分块拉取下位机文件（内建单包 CRC32 物理防损）"""
        open_res = self.dispatcher.request_sync(
            dto.CmdReadOpen, path=remote_path)
        sid = open_res.session_id
        total_size = open_res.file_size
        offset = 0

        try:
            with open(local_path, 'wb') as f:
                while offset < total_size:
                    # 分块读取请求，单包请求 8192 字节
                    data_res = self.dispatcher.request_sync(
                        dto.CmdReadData,
                        session_id=sid,
                        offset=offset,
                        size=8192
                    )

                    chunk = data_res.binary_data
                    remote_crc32 = data_res.crc32
                    local_crc32 = zlib.crc32(chunk) & 0xFFFFFFFF

                    if remote_crc32 != 0 and local_crc32 != remote_crc32:
                        raise NvsFileIOError(
                            f"分包 CRC32 物理校验失败, 错误偏移位置: {offset}")

                    f.write(chunk)
                    offset += len(chunk)

                    if progress_callback:
                        progress_callback(offset, total_size)

            self.dispatcher.request_sync(dto.CmdClose, session_id=sid)

        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            try:
                self.dispatcher.request_sync(
                    dto.CmdClose, session_id=sid, timeout=1.0)
            except Exception:
                pass
            raise NvsFileIOError(f"文件流式读取异常中断: {str(e)}") from e

        return True
