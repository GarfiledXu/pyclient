import os
import json
import zlib
import hashlib
import random
from loguru import logger


# class FileIOTester:
#     def __init__(self, client):
#         self.client = client

#     def get_md5(self, data):
#         return hashlib.md5(data).hexdigest()

#     def generate_test_file(self, local_path, size_bytes):
#         data = os.urandom(size_bytes)
#         with open(local_path, 'wb') as f:
#             f.write(data)
#         return self.get_md5(data)

#     def upload_file(self, local_path, remote_path):
#         with open(local_path, 'rb') as f:
#             content = f.read()
#         local_md5 = self.get_md5(content)
#         self.client.send_cmd("File_SVC_Write_Open", {
#                              "path": remote_path, "total_size": len(content), "md5": local_md5})
#         res = self.client.wait_for_response("File_SVC_Write_Open")
#         if res['cmd'] == "ER":
#             return False

#         sid = json.loads(res['payload'])['session_id']
#         offset, step = 0, 4096
#         while offset < len(content):
#             chunk = content[offset: offset + step]
#             self.client.send_binary("File_SVC_Write_Data", {"session_id": sid, "offset": offset, "data_len": len(
#                 chunk), "crc32": zlib.crc32(chunk) & 0xFFFFFFFF}, chunk)
#             self.client.wait_for_response("File_SVC_Write_Data")
#             offset += step

#         self.client.send_cmd("File_SVC_Close", {"session_id": sid})
#         self.client.wait_for_response("File_SVC_Close")
#         return True

#     def download_file(self, remote_path, local_path):
#         self.client.send_cmd("File_SVC_Read_Open", {"path": remote_path})
#         res = self.client.wait_for_response("File_SVC_Read_Open")
#         if res['cmd'] == "ER":
#             return False

#         meta = json.loads(res['payload'])
#         sid, total_size = meta['session_id'], meta['file_size']
#         file_data = bytearray()
#         offset = 0
#         while offset < total_size:
#             self.client.send_cmd("File_SVC_Read_Data", {
#                                  "session_id": sid, "offset": offset, "size": 8192})
#             res_d = self.client.wait_for_response("File_SVC_Read_Data")
#             file_data.extend(res_d['binary'])
#             offset += len(res_d['binary'])

#         self.client.send_cmd("File_SVC_Close", {"session_id": sid})
#         self.client.wait_for_response("File_SVC_Close")
#         return True

import hashlib
import os
import zlib
from loguru import logger
import nvs_cmd_dto as dto  # 引入 DTO 结构定义


class NvsFileIOError(Exception):
    """NVS专属的文件传输异常"""
    pass


class NvsFileSvc:
    """NVS 文件传输服务 (对齐下位机 File_SVC 模块)"""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def calculate_md5(file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def generate_test_file(local_path, size_bytes):
        chunk_size = 1024 * 1024
        with open(local_path, 'wb') as f:
            remaining = size_bytes
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(os.urandom(write_size))
                remaining -= write_size
        return NvsFileSvc.calculate_md5(local_path)

    def write(self, local_path: str, remote_path: str) -> bool:
        """[写入操作] 纯对象化交互流程"""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"本地文件不存在: {local_path}")

        file_size = os.path.getsize(local_path)
        local_md5 = self.calculate_md5(local_path)

        # 1. 开启写会话
        open_res = self.client.request_dto(
            dto.CmdWriteOpen,
            path=remote_path,
            total_size=file_size,
            md5=local_md5
        )
        sid = open_res.session_id

        step = 4096
        offset = 0

        # 2. 流式传输数据
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

            # 3. 正常关闭会话
            self.client.request_dto(dto.CmdClose, session_id=sid)

        except Exception as e:
            try:
                self.client.request_dto(dto.CmdClose, session_id=sid)
                self.client.request_dto(dto.CmdDelete, path=remote_path)
            except Exception:
                pass
            raise NvsFileIOError(f"写入过程异常中断: {str(e)}")

        # 4. 闭环校验 MD5
        stat_res = self.client.request_dto(dto.CmdStat, path=remote_path)
        if stat_res.md5 != local_md5:
            self.client.request_dto(dto.CmdDelete, path=remote_path)
            raise NvsFileIOError(
                f"完整性校验失败！期望: {local_md5}, 实际: {stat_res.md5}")

        return True

    def read(self, remote_path: str, local_path: str) -> bool:
        """[读取操作] 纯对象化交互流程"""
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
                        raise NvsFileIOError(
                            f"单包 CRC32 失败！Offset: {offset}, 本地: {local_crc32}, 远端: {remote_crc32}")

                    f.write(chunk)
                    offset += len(chunk)

            self.client.request_dto(dto.CmdClose, session_id=sid)

        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            try:
                self.client.request_dto(dto.CmdClose, session_id=sid)
            except Exception:
                pass
            raise NvsFileIOError(f"读取过程崩溃: {str(e)}")

        return True
