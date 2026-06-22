from dataclasses import dataclass, field
from typing import List, Dict, Any


class BaseCmd:
    """业务层：所有协议报文指令 DTO 的基类，用于自动建立映射表"""
    registry = {}

    def __init_subclass__(cls, cmd_name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.registry[cmd_name] = cls
        cls.CMD_NAME = cmd_name

# ==============================================================================
# FILE_SVC 文件子系统业务指令
# ==============================================================================


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
        files: List[Dict[str, Any]]


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
        # 拦截大块二进制数据，严禁打印引发刷屏
        binary_data: bytes = field(default=b'', repr=False)


class CmdWriteOpen(BaseCmd, cmd_name="File_SVC_Write_Open"):
    @dataclass
    class Req:
        path: str
        total_size: int
        md5: str

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
        # 发送载荷
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

# ==============================================================================
# BACKUP 备份业务子系统业务指令
# ==============================================================================


class CmdBackupManifestQuery(BaseCmd, cmd_name="Backup_Manifest_Query"):
    @dataclass
    class Req:
        pass

    @dataclass
    class Res:
        roots: List[str]
        files: List[Dict[str, Any]]
