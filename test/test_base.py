import pytest
import bak.nvs_cmd_dto as dto
from bak.nvs_client import NvsBusinessError, NvsTimeoutError

# ==========================================
# 测试环境“宏定义”配置区
# ==========================================
CFG_ROOT_DIR = "/oem/cfg"
CFG_TEST_MKDIR_PATH = "/tmp/test_api_dir/"
CFG_EXISTING_FILE = "/tmp/test_stat.bin"
CFG_NON_EXISTENT_FILE = "/tmp/ghost_file.json"


class TestBasicAPI:
    """原子级（一发一收）无状态 API 测试集"""

    def test_cap_query(self, client):
        """
        [Cmd] CmdCapQuery
        验证：下位机能力查询接口。
        检查点：max_chunk_size 必须为正整数，root_paths 必须是目录列表。
        """
        res = client.request_dto(dto.CmdCapQuery)
        assert res.max_chunk_size > 0
        assert isinstance(res.root_paths, list)

    def test_mkdir_and_delete(self, client):
        """
        [Cmd] CmdMkdir / CmdDelete
        验证：目录管理原子操作。
        流程：1. 创建指定路径目录 -> 2. 立即删除该目录。
        """
        # 验证创建
        client.request_dto(dto.CmdMkdir, path=CFG_TEST_MKDIR_PATH)
        # 验证删除
        client.request_dto(dto.CmdDelete, path=CFG_TEST_MKDIR_PATH)

    def test_list_directory(self, client):
        """
        [Cmd] CmdList
        验证：目录内容遍历接口。
        检查点：递归查询指定路径，返回的文件对象列表必须符合预期格式。
        """
        res = client.request_dto(
            dto.CmdList,
            path=CFG_ROOT_DIR,
            recursive=1,
            max_count=5,
            cursor=0
        )
        assert isinstance(res.files, list)

    def test_stat_existing_file(self, client):
        """
        [Cmd] CmdStat (正向)
        验证：已有文件的元数据查询。
        检查点：获取文件 Size 和 MD5。如果文件不存在或链路故障，则反馈失败。
        """
        res = client.request_dto(dto.CmdStat, path=CFG_EXISTING_FILE)
        assert res.size >= 0
        assert len(res.md5) == 32

    def test_stat_error_handling(self, client):
        """
        [Cmd] CmdStat (异常) / ER 拦截
        验证：非法路径下的错误拦截机制。
        检查点：当路径不存在时，下位机必须回传 ER 报文。
        解析：提取 NvsBusinessError 里的模块名和错误码是否符合协议规范。
        """
        with pytest.raises(NvsBusinessError) as exc_info:
            client.request_dto(dto.CmdStat, path=CFG_NON_EXISTENT_FILE)

        err = exc_info.value
        assert err.module == "File_SVC_STAT"
        # 根据你实际拿到的 101 进行断言
        assert err.error_code == "101"
        print(f"\n捕获到预期业务错误: {err}")

    def test_communication_timeout_logic(self, client):
        """
        [Protocol] Timeout Handling
        验证：通信链路监控机制。
        说明：模拟指令无响应场景（通过 wait_for_response 超时触发）。
        预期：抛出 NvsTimeoutError。
        """
        # 演示用途，不执行具体逻辑
        pass


"""
================================================================================
测试模块: TestBasicAPI (基础协议原子测试)
================================================================================
[描述]
    本脚本用于验证 NVS 通信协议中最基础的“一发一收”无状态指令。
    确保底层 DTO 序列化、通信链路稳定性以及下位机基础业务逻辑的正确性。

[依赖环境]
    1. 下位机必须处于待机/就绪状态。
    2. 下位机文件系统需挂载，且存在测试桩文件 (CFG_EXISTING_FILE)。
    3. 通信参数 (IP/Port/Serial) 已在 pytest.ini 或 conftest.py 中配置。

[涵盖协议指令 (Cmd)]
    - CmdCapQuery    : 设备能力查询 (版本、分片大小、根路径)
    - CmdMkdir       : 目录创建
    - CmdDelete      : 文件/目录删除
    - CmdList        : 目录列表获取 (支持递归和分页)
    - CmdStat        : 文件元数据查询 (Size, MD5)

[错误处理逻辑]
    - NvsTimeoutError  : 验证通信层，当对方在指定时间内未回包时触发。
    - NvsBusinessError : 验证业务层，当下位机显式返回 ER 报文时触发，支持错误码解析。
================================================================================
"""
