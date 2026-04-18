# from dataclasses import dataclass, field

# # ==========================================
# # 核心引擎：支持 IDE 折叠预览的自动注册基类
# # ==========================================


# class BaseCmd:
#     """
#     所有指令 DTO 的基类。
#     利用 __init_subclass__ 实现自动注册，强制要求传入 cmd_name 参数。
#     """
#     registry = {}

#     def __init_subclass__(cls, cmd_name: str, **kwargs):
#         super().__init_subclass__(**kwargs)
#         # 1. 注册到全局路由表
#         cls.registry[cmd_name] = cls
#         # 2. 将名字挂载为静态属性，供底层协议引擎读取
#         cls.CMD_NAME = cmd_name


# # ==========================================
# # 业务 DTO 定义：折叠代码即可获得完美的全局指令目录
# # ==========================================

# class CmdWriteOpen(BaseCmd, cmd_name="File_SVC_Write_Open"):
#     @dataclass
#     class Req:
#         path: str
#         total_size: int
#         md5: str

#     @dataclass
#     class Res:
#         session_id: str


# class CmdWriteData(BaseCmd, cmd_name="File_SVC_Write_Data"):
#     @dataclass
#     class Req:
#         session_id: str
#         offset: int
#         data_len: int
#         crc32: int
#         # 携带发往 MCU 的二进制块，禁止在控制台打印乱码
#         binary_data: bytes = field(default=b'', repr=False)

#     @dataclass
#     class Res:
#         pass


# class CmdReadOpen(BaseCmd, cmd_name="File_SVC_Read_Open"):
#     @dataclass
#     class Req:
#         path: str

#     @dataclass
#     class Res:
#         session_id: str
#         file_size: int


# class CmdReadData(BaseCmd, cmd_name="File_SVC_Read_Data"):
#     @dataclass
#     class Req:
#         session_id: str
#         offset: int
#         size: int

#     @dataclass
#     class Res:
#         # MCU 返回的单包校验和，给默认值防崩溃
#         crc32: int = 0
#         # 接收 MCU 传回来的二进制块
#         binary_data: bytes = field(default=b'', repr=False)


# class CmdClose(BaseCmd, cmd_name="File_SVC_Close"):
#     @dataclass
#     class Req:
#         session_id: str

#     @dataclass
#     class Res:
#         pass


# class CmdStat(BaseCmd, cmd_name="File_SVC_STAT"):
#     @dataclass
#     class Req:
#         path: str

#     @dataclass
#     class Res:
#         md5: str
#         # 视 MCU 固件而定，如果有 file_size 就解析，没有就默认 0
#         file_size: int = 0


# class CmdDelete(BaseCmd, cmd_name="File_SVC_Delete"):
#     @dataclass
#     class Req:
#         path: str

#     @dataclass
#     class Res:
#         pass

from dataclasses import dataclass, field
from typing import List, Dict, Any


class BaseCmd:
    """
    所有指令 DTO 的基类。
    利用 __init_subclass__ 实现自动注册，强制要求传入 cmd_name 参数。
    """
    registry = {}

    def __init_subclass__(cls, cmd_name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.registry[cmd_name] = cls
        cls.CMD_NAME = cmd_name

# ==========================================
# 1. 基础查询功能
# ==========================================


class CmdCapQuery(BaseCmd, cmd_name="File_SVC_CAP_Query"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        max_chunk_size: int
        support_compress: list
        root_paths: list


class CmdStat(BaseCmd, cmd_name="File_SVC_STAT"):
    @dataclass
    class Req:
        path: str

    @dataclass
    class Res:
        path: str = ""
        size: int = 0
        md5: str = ""


class CmdList(BaseCmd, cmd_name="File_SVC_List"):
    @dataclass
    class Req:
        path: str
        recursive: int
        max_count: int
        cursor: int

    @dataclass
    class Res:
        file_count: int
        has_more: int
        next_cursor: int
        files: list  # 内部是 dict: {"path": "/x/", "is_dir": 1}

# ==========================================
# 2. 文件传输 (Read / Write)
# ==========================================


class CmdReadOpen(BaseCmd, cmd_name="File_SVC_Read_Open"):
    @dataclass
    class Req:
        path: str

    @dataclass
    class Res:
        session_id: int
        file_size: int


class CmdReadData(BaseCmd, cmd_name="File_SVC_Read_Data"):
    @dataclass
    class Req:
        session_id: int
        offset: int
        size: int

    @dataclass
    class Res:
        offset: int = 0
        data_len: int = 0
        is_eof: int = 0
        crc32: int = 0
        # 接收 MCU 传回来的二进制块
        binary_data: bytes = field(default=b'', repr=False)


class CmdWriteOpen(BaseCmd, cmd_name="File_SVC_Write_Open"):
    @dataclass
    class Req:
        path: str
        total_size: int
        md5: str        # 补齐了丢失的 MD5 字段

    @dataclass
    class Res:
        session_id: int


class CmdWriteData(BaseCmd, cmd_name="File_SVC_Write_Data"):
    @dataclass
    class Req:
        session_id: int
        offset: int
        data_len: int
        crc32: int
        # 携带发往 MCU 的二进制块，禁止在控制台打印乱码
        binary_data: bytes = field(default=b'', repr=False)

    @dataclass
    class Res:
        written: int = 0
        status: int = 0


class CmdClose(BaseCmd, cmd_name="File_SVC_Close"):
    @dataclass
    class Req:
        session_id: int

    @dataclass
    class Res:
        pass

# ==========================================
# 3. 文件及目录操作
# ==========================================


class CmdDelete(BaseCmd, cmd_name="File_SVC_Delete"):
    @dataclass
    class Req:
        path: str

    @dataclass
    class Res:
        pass


class CmdMkdir(BaseCmd, cmd_name="File_SVC_MKDIR"):
    @dataclass
    class Req:
        path: str

    @dataclass
    class Res:
        pass

# ==========================================
# 4. 备份业务流控制
# ==========================================


class CmdBackupManifestQuery(BaseCmd, cmd_name="Backup_Manifest_Query"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        roots: list
        files: list


class CmdBackupExportStart(BaseCmd, cmd_name="Backup_Export_Start"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        pass


class CmdBackupExportEnd(BaseCmd, cmd_name="Backup_Export_End"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        pass


class CmdBackupImportStart(BaseCmd, cmd_name="Backup_Import_Start"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        pass


class CmdBackupImportEnd(BaseCmd, cmd_name="Backup_Import_End"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        pass
