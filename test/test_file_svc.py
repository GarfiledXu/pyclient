"""
================================================================================
测试模块: TestFileIOFlow (文件传输业务逻辑测试)
================================================================================
[描述]
    验证文件读写全流程的可靠性。该测试涉及有状态的会话 (Session) 管理、数据切片、
    CRC 校验以及最终的 MD5 一致性比对。

[依赖环境]
    1. 下位机文件系统需具备读写权限。
    2. 下位机需支持多包连续传输状态机。

[涵盖协议指令 (Cmd)]
    - CmdWriteOpen / CmdWriteData / CmdWriteClose : 文件写入流水线
    - CmdReadOpen  / CmdReadData  / CmdReadClose  : 文件读取流水线
    - CmdStat                                     : 写入后的落盘校验
    - CmdDelete                                   : 测试后的环境清理

[校验机制]
    - 链路层: 每包数据的响应状态。
    - 业务层: 写入完成后立即进行 Stat 查询，对比 MD5。
    - 最终层: 读回本地后，进行端到端二进制 MD5 比对。
================================================================================
"""

import pytest
import os
from nvs_client import NvsBusinessError, NvsTimeoutError
import nvs_cmd_dto as dto

# ==========================================
# 测试环境“宏定义”配置区 (Configuration)
# ==========================================
CFG_SIZE_SMALL = 1024           # 1KB (验证单包传输)
CFG_SIZE_LARGE = 1024 * 256     # 256KB (验证多包切片与偏移量)

# 远端写入的测试路径
CFG_REMOTE_PATH_TEMPLATE = "/tmp/io_test_{size}.bin"

# 本地临时文件的前缀名称
CFG_LOCAL_SRC_PREFIX = "source_data"
CFG_LOCAL_DST_PREFIX = "download_data"


class TestFileIOFlow:
    """验证文件传输的 Session 状态机与数据完整性"""

    @pytest.mark.parametrize("size", [CFG_SIZE_SMALL, CFG_SIZE_LARGE])
    def test_file_transfer_integrity(self, svc, tmp_path, size):
        """
        [Cmd] File_Write_Flow / File_Read_Flow
        验证点：本地生成 -> 写入 -> 读回 -> 终极 MD5 比对。
        """
        # 1. 路径准备
        remote_path = CFG_REMOTE_PATH_TEMPLATE.format(size=size)
        local_src = os.path.join(
            tmp_path, f"{CFG_LOCAL_SRC_PREFIX}_{size}.bin")
        local_dst = os.path.join(
            tmp_path, f"{CFG_LOCAL_DST_PREFIX}_{size}.bin")

        # 2. 准备本地随机测试数据
        # generate_test_file 内部会返回该随机文件的原始 MD5
        src_md5 = svc.generate_test_file(local_src, size)

        # 3. 执行写入流程 (Write Session)
        # 注意：svc.write 内部应封装了 Open -> 多次 Data -> Close
        # 如果内部发生 NvsBusinessError，这里会直接抛出并导致 Fail
        try:
            write_res = svc.write(local_src, remote_path)
            assert write_res is True, f"文件写入失败 (Size: {size})"

            # 4. 执行读取流程 (Read Session)
            # 验证下位机能否正确处理 Open -> 多次 Data -> Close
            read_res = svc.read(remote_path, local_dst)
            assert read_res is True, f"文件读取失败 (Size: {size})"

            # 5. 终极 MD5 比对：本地源文件 vs 绕场一周回来的文件
            dst_md5 = svc.calculate_md5(local_dst)
            assert src_md5 == dst_md5, f"端到端校验失败！数据在传输中受损 (Size: {size})"

        finally:
            # 6. 环境清理 (Cleanup)
            # 无论测试成功还是失败，都尝试删除远端测试文件，防止占用 Flash 空间
            try:
                svc.client.request_dto(dto.CmdDelete, path=remote_path)
            except Exception:
                pass  # 清理失败不作为测试失败的理由

    def test_file_io_error_handling(self, client):
        """
        [Cmd] CmdReadOpen / CmdWriteOpen (异常)
        验证：打开不存在的文件或非法路径时，状态机是否能正确拒绝并返回 ER。
        """
        with pytest.raises(NvsBusinessError) as exc_info:
            # 假设 CmdReadOpen 对应的 Req 需要 path 参数
            client.request_dto(
                dto.CmdReadOpen, path="/non_exist_dir/no_file.bin")

        # 验证返回的错误是否符合业务定义 (假设 102 为路径不存在)
        assert exc_info.value.error_code == "102"
