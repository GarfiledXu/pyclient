import os
import json
import dataclasses
import time
from pathlib import Path

import nvs_cmd_dto as dto
# 假设你在 conftest.py 注册了 --action 参数
# 连接设备 A，运行导出任务：
# pytest tests/test_migration.py --action=export --vault-name=device_A_golden
# 拔掉 A，连上设备 B，运行导入任务：
# pytest tests/test_migration.py --action=import --vault-name=device_A_golden


class BackupMigrationManager:
    """处理跨设备备份迁移的业务管理器"""

    def __init__(self, client, svc, vault_root: Path):
        self.client = client
        self.svc = svc
        self.vault_root = vault_root
        self.vault_root.mkdir(parents=True, exist_ok=True)

    def do_export(self, label: str):
        """
        [导出动作] 从当前连接设备抓取文件
        label: 给这次导出打个标签，比如 'source_device_A' 或 'target_pre_backup'
        """
        vault_path = self.vault_root / label
        vault_path.mkdir(parents=True, exist_ok=True)

        # 1. 查询清单
        manifest = self.client.request_dto(dto.CmdBackupManifestQuery)

        # 2. 保存清单快照 (Import 时需要读取)
        manifest_path = vault_path / "manifest_snapshot.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(manifest), f, indent=4)

        if len(manifest.files) == 0:
            print(f"提示: 设备 [{label}] 清单为空，无需下载。")
            return vault_path

        # 3. 搬运数据
        self.client.request_dto(dto.CmdBackupExportStart)
        try:
            for file_info in manifest.files:
                root_prefix = manifest.roots[file_info['roots_idx']]
                rel_path = file_info['relative_path']

                remote_src = os.path.join(
                    root_prefix, rel_path).replace("\\", "/")
                # 本地路径增加 roots_idx 层级防止同名冲突
                local_dest = vault_path / \
                    str(file_info['roots_idx']) / rel_path
                local_dest.parent.mkdir(parents=True, exist_ok=True)

                print(f"[{label}] 正在拉取: {rel_path}")
                self.svc.read(remote_src, str(local_dest))
        finally:
            self.client.request_dto(dto.CmdBackupExportEnd)

        print(f"✅ 导出成功！路径: {vault_path}")
        return vault_path

    def do_import(self, source_vault_label: str, use_shadow=True):
        """
        [导入动作] 将指定的本地金库数据灌入当前设备
        source_vault_label: 使用哪个导出的包作为源
        """
        source_path = self.vault_root / source_vault_label
        manifest_path = source_path / "manifest_snapshot.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"找不到源金库清单: {manifest_path}")

        # 1. 🌟 安全保障：导入前先给当前设备（目标设备）做一次强制备份
        recovery_label = f"recovery_before_{source_vault_label}_{int(time.time())}"
        print(f"⚠️ 正在执行导入前自动备份，恢复包标签: {recovery_label}")
        self.do_export(recovery_label)

        # 2. 读取源清单数据
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        # 3. 处理路径映射 (Shadow Root)
        roots = manifest_data['roots']
        if use_shadow:
            roots = [os.path.join(
                "/tmp/shadow_vault", r.lstrip("/")).replace("\\", "/") for r in roots]

        # 4. 执行上传
        self.client.request_dto(dto.CmdBackupImportStart)
        try:
            for file_info in manifest_data['files']:
                root_prefix = roots[file_info['roots_idx']]
                rel_path = file_info['relative_path']

                local_src = source_path / \
                    str(file_info['roots_idx']) / rel_path
                remote_dest = os.path.join(
                    root_prefix, rel_path).replace("\\", "/")

                if local_src.exists():
                    print(f"正在恢复: {rel_path} -> {remote_dest}")
                    self.svc.write(str(local_src), remote_dest)
        finally:
            self.client.request_dto(dto.CmdBackupImportEnd)

        print(f"✅ 导入完成！")
