"""
================================================================================
测试模块: TestBackupBusinessFlow (具备分层结构的备份与恢复业务测试)
================================================================================
[描述]
    模拟完整业务场景：获取 roots 分层清单，在本地创建索引文件夹镜像，执行下载与还原。

[路径规则]
    1. 远端绝对路径 = Manifest.roots[roots_idx] + relative_path
    2. 本地存储结构 = 备份根目录 / {roots_idx} / {relative_path}
    3. 清单保存路径 = 备份根目录 / manifest.json

[涵盖协议指令 (Cmd)]
    - CmdBackupManifestQuery : 获取分层清单
    - CmdBackupExportStart/End : 导出状态机切换
    - CmdBackupImportStart/End : 导入状态机切换
    - File_SVC (Read/Write)  : 物理搬运 (需拼接绝对路径)
================================================================================
"""

import pytest
import os
import json
import bak.nvs_cmd_dto as dto
from bak.nvs_client import NvsBusinessError, NvsTimeoutError
import dataclasses  # 核心修复点：确保全局可用
import bak.nvs_cmd_dto as dto

# # ==========================================
# # 测试环境“宏定义”配置区 (Configuration)
# # ==========================================
# # 存放从 MCU 下载的备份文件的本地临时文件夹名称
# CFG_LOCAL_VAULT_NAME = "mcu_backup_vault"


# class TestBackupBusinessFlow:
#     """模拟备份与恢复的完整业务流"""

#     def test_full_backup_and_restore_cycle(self, client, svc, tmp_path):
#         """
#         [Cmd] Backup_Lifecycle_with_Hierarchy
#         全链路测试：处理 roots 索引分层、目录递归创建、清单本地化
#         """

#         # 1. 在指定的临时目录下创建一个专属的“备份金库”文件夹
#         backup_vault = tmp_path / CFG_LOCAL_VAULT_NAME
#         backup_vault.mkdir(parents=True, exist_ok=True)

#         # ==========================================
#         # 1. 导出阶段 (Export - 从 MCU 拉取备份)
#         # ==========================================

#         # 1.1 [Cmd] CmdBackupManifestQuery: 获取分层清单
#         manifest = client.request_dto(dto.CmdBackupManifestQuery)
#         assert isinstance(manifest.files, list), "清单格式错误：files 必须是列表"

#         # 将原始清单保存到本地，供后续恢复流程使用或人工比对
#         manifest_path = backup_vault / "manifest.json"
#         with open(manifest_path, "w", encoding="utf-8") as f:
#             # 假设 DTO 有 to_dict 方法，或者使用 dataclasses.asdict
#             import dataclasses
#             json.dump(dataclasses.asdict(manifest), f, indent=4)

#         if len(manifest.files) == 0:
#             pytest.skip("MCU 当前备份清单为空，跳过数据搬运测试")

#         # 1.2 [Cmd] CmdBackupExportStart: 开启导出信号
#         client.request_dto(dto.CmdBackupExportStart)

#         try:
#             # 1.3 遍历清单，执行物理数据搬运
#             for file_info in manifest.files:
#                 # 解析索引对应的根路径
#                 root_prefix = manifest.roots[file_info['roots_idx']]
#                 rel_path = file_info['relative_path']
#                 expected_md5 = file_info['md5']

#                 # 合成远端绝对路径 (用于 Read_Open)
#                 remote_abs_path = os.path.join(
#                     root_prefix, rel_path).replace("\\", "/")

#                 # 合成本地分层路径: vault / {idx} / {rel_path}
#                 local_file_path = backup_vault / \
#                     str(file_info['roots_idx']) / rel_path

#                 # 递归创建本地目录结构 (含索引文件夹)
#                 local_file_path.parent.mkdir(parents=True, exist_ok=True)

#                 # 使用业务引擎下载
#                 read_success = svc.read(remote_abs_path, str(local_file_path))
#                 assert read_success is True, f"下载备份文件失败: {remote_abs_path}"

#                 # 校验 MD5 完整性
#                 actual_md5 = svc.calculate_md5(str(local_file_path))
#                 assert actual_md5 == expected_md5, \
#                     f"文件 {rel_path} 损坏！期望: {expected_md5}, 实际: {actual_md5}"

#         finally:
#             # 1.4 [Cmd] CmdBackupExportEnd: 释放资源
#             client.request_dto(dto.CmdBackupExportEnd)

#         # ==========================================
#         # 2. 导入阶段 (Import - 将备份推回 MCU)
#         # ==========================================

#         # 2.1 [Cmd] CmdBackupImportStart: 开启导入信号
#         client.request_dto(dto.CmdBackupImportStart)

#         try:
#             # 2.2 遍历本地备份镜像，推回给 MCU
#             for file_info in manifest.files:
#                 root_prefix = manifest.roots[file_info['roots_idx']]
#                 rel_path = file_info['relative_path']

#                 remote_abs_path = os.path.join(
#                     root_prefix, rel_path).replace("\\", "/")
#                 local_file_path = backup_vault / \
#                     str(file_info['roots_idx']) / rel_path

#                 assert local_file_path.exists(), f"本地镜像丢失: {local_file_path}"

#                 # 使用业务引擎上传 (内部自带 Stat 校验)
#                 write_success = svc.write(
#                     str(local_file_path), remote_abs_path)
#                 assert write_success is True, f"恢复备份文件失败: {remote_abs_path}"

#         finally:
#             # 2.3 [Cmd] CmdBackupImportEnd: 提交修改
#             client.request_dto(dto.CmdBackupImportEnd)

#     def test_backup_manifest_error(self, client):
#         """
#         [Cmd] CmdBackupManifestQuery (异常拦截)
#         验证：当下位机存储介质故障时，提取 NvsBusinessError 里的业务错误码。
#         """
#         # 验证点：此时应抛出 NvsBusinessError 而非超时或代码崩溃
#         pass

# ==========================================
# 测试环境“宏定义”配置区 (Configuration)
# ==========================================
# 本地临时缓存文件夹名称
CFG_LOCAL_VAULT_NAME = "backup_vault"

# 🌟【核心开关】：影子重定向
# True:  物理路径会被重定向到安全目录 (如 /tmp/shadow_vault/oem/cfg/...)
# False: 彻底真实替换，直接覆盖系统原路径 (如 /oem/cfg/...)
CFG_USE_SHADOW_MAPPING = True
CFG_SHADOW_ROOT = "/tmp/shadow_vault"


class TestBackupBusinessFlow:
    """模拟备份与恢复的完整业务流"""

    def test_full_backup_and_restore_cycle(self, client, svc, tmp_path):
        """
        [Cmd] Backup_Lifecycle_with_Shadow_Mapping
        全链路测试：处理 roots 索引分层、目录递归创建、清单本地化
        """

        # 1. 在 Pytest 临时目录下创建一个专属的本地“备份金库”文件夹
        # local_backup_vault 是你在 PC 端的临时仓库
        local_backup_vault = tmp_path / CFG_LOCAL_VAULT_NAME
        local_backup_vault.mkdir(parents=True, exist_ok=True)

        # ==========================================
        # 1. 导出阶段 (Export - 从 MCU 拉取备份)
        # ==========================================

        # 1.1 [Cmd] CmdBackupManifestQuery: 获取分层清单
        manifest = client.request_dto(dto.CmdBackupManifestQuery)
        assert isinstance(manifest.files, list), "清单格式错误：files 必须是列表"

        # 将原始清单保存到本地，方便调试对比
        manifest_path = local_backup_vault / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(manifest), f, indent=4)

        if len(manifest.files) == 0:
            pytest.skip("MCU 当前备份清单为空，跳过数据搬运测试")

        # 1.2 [Cmd] CmdBackupExportStart: 开启导出信号
        client.request_dto(dto.CmdBackupExportStart)

        try:
            # 1.3 遍历清单，执行物理数据搬运
            for file_info in manifest.files:
                # 获取该文件在 MCU 上的根路径前缀
                root_prefix = manifest.roots[file_info['roots_idx']]
                rel_path = file_info['relative_path']
                expected_md5 = file_info['md5']

                # 合成远端绝对路径 (用于 Read_Open)
                remote_src_path = os.path.join(
                    root_prefix, rel_path).replace("\\", "/")

                # 合成本地分层路径: vault / {idx} / {rel_path}
                local_file_path = local_backup_vault / \
                    str(file_info['roots_idx']) / rel_path

                # 递归创建本地目录结构 (确保 0/, 1/ 等索引文件夹及子目录存在)
                local_file_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用业务引擎下载
                read_success = svc.read(remote_src_path, str(local_file_path))
                assert read_success is True, f"下载备份文件失败: {remote_src_path}"

                # 校验 MD5 完整性
                actual_md5 = svc.calculate_md5(str(local_file_path))
                assert actual_md5 == expected_md5, \
                    f"文件 {rel_path} 数据损坏！期望: {expected_md5}, 实际: {actual_md5}"
        finally:
            # 1.4 释放 MCU 导出资源
            client.request_dto(dto.CmdBackupExportEnd)

        # ==========================================
        # 2. 导入阶段 (Import - 将备份推回 MCU)
        # ==========================================

        # 🌟 核心逻辑：影子映射处理
        # 如果开启开关，我们直接在内存中篡改 manifest 对象的 roots 列表
        # 这使得后续循环中的 os.path.join 能够透明地生成重定向后的物理路径
        if CFG_USE_SHADOW_MAPPING:
            original_roots = list(manifest.roots)
            # 将每个 root 加上影子前缀，并确保路径分隔符正确
            # 例子: /oem/cfg -> /tmp/shadow_vault/oem/cfg
            manifest.roots = [
                os.path.join(CFG_SHADOW_ROOT, r.lstrip("/")).replace("\\", "/")
                for r in original_roots
            ]
            print(f"\n[INFO] 影子映射已激活，文件将恢复至: {CFG_SHADOW_ROOT}")

        # 2.1 [Cmd] CmdBackupImportStart: 开启导入信号
        client.request_dto(dto.CmdBackupImportStart)

        try:
            # 2.2 遍历本地镜像，推回给 MCU
            for file_info in manifest.files:
                # 这里的 root_prefix 可能是原路径，也可能是被篡改后的影子路径
                root_prefix = manifest.roots[file_info['roots_idx']]
                rel_path = file_info['relative_path']

                # 合成物理目标路径
                remote_dest_path = os.path.join(
                    root_prefix, rel_path).replace("\\", "/")
                # 找到本地对应的镜像文件
                local_file_path = local_backup_vault / \
                    str(file_info['roots_idx']) / rel_path

                assert local_file_path.exists(), f"本地镜像丢失: {local_file_path}"

                # 执行上传 (svc.write 内部会自动处理 Open/Data/Close/Stat)
                write_success = svc.write(
                    str(local_file_path), remote_dest_path)
                assert write_success is True, f"恢复备份文件失败: {remote_dest_path}"
        finally:
            # 2.3 [Cmd] CmdBackupImportEnd: 提交修改 (底层已处理 04 Busy 自动重试)
            client.request_dto(dto.CmdBackupImportEnd)

    def test_backup_manifest_error(self, client):
        """
        [Cmd] CmdBackupManifestQuery (异常拦截)
        验证：当下位机存储介质故障时，提取 NvsBusinessError 里的业务错误码。
        """
        pass
