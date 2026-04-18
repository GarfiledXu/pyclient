# tests/test_migration.py
import pytest
from util.backup_tools import BackupMigrationManager

# pytest tests/test_migration.py --action=export --vault=device_a_v1
# pytest tests/test_migration.py --action=import --vault=device_a_v1


class TestDeviceMigration:

    def test_migration_dispatch(self, client, svc, run_config):
        # 1. 拿到配置
        action = run_config["action"]
        vault_name = run_config["vault"]
        vault_root = run_config["vault_root"]

        print(f"\n[测试信息] 动作: {action}")
        print(f"[测试信息] 金库存放在: {vault_root}")
        print(f"[测试信息] 当前数据包: {vault_name}")

        # 2. 初始化你的业务管理器
        manager = BackupMigrationManager(client, svc, vault_root)

        # 3. 分发任务
        if action == "export":
            manager.do_export(label=vault_name)
        elif action == "import":
            manager.do_import(source_vault_label=vault_name, use_shadow=True)
        else:
            pytest.skip("没有指定有效动作，跳过测试")
