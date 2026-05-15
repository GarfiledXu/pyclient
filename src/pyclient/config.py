import sys
from pathlib import Path
from importlib import resources

# 自动处理 Python 3.11 以下的 tomllib 兼容性
try:
    import tomllib
except ImportError:
    import tomli as tomllib


class ConfigLoader:
    """配置加载器：负责寻找并合并包内/外部配置"""

    @staticmethod
    def get_root_dir() -> Path:
        """从当前文件位置逆推项目根目录 (src/pyclient/config.py -> PYCLIENT/)"""
        return Path(__file__).resolve().parents[2]

    @classmethod
    def load_all(cls) -> dict:
        """加载流程：1. 包内保底 -> 2. 外部覆盖"""
        # --- A. 加载包内出厂默认 (必须存在) ---
        try:
            # 这里的 pyclient.asset 是你的单数命名包名
            base_text = resources.read_text("pyclient.asset", "default.toml")
            config = tomllib.loads(base_text)
        except Exception as e:
            sys.stderr.write(f"[严重错误] 无法读取包内默认配置: {e}\n")
            config = {}

        # --- B. 合并外部用户配置 (config/config.toml) ---
        user_path = cls.get_root_dir() / "config" / "config.toml"
        if user_path.exists():
            try:
                with open(user_path, "rb") as f:
                    user_data = tomllib.load(f)
                    # 增量合并：用户改了哪项，就覆盖哪项
                    # 注意：如果 TOML 结构很深，建议在此处实现递归合并函数
                    config.update(user_data)
            except Exception as e:
                # 此时 logger 可能未就绪，使用 stderr 打印
                sys.stderr.write(f"[警告] 加载外部配置文件失败: {e}\n")

        return config


# --- 全局唯一配置出口 ---
cfg = ConfigLoader.load_all()
