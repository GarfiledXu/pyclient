import sys
from pathlib import Path
from dataclasses import dataclass, field

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# ==============================================================================
# 1. 基础结构体定义
# ==============================================================================

@dataclass
class LogFinalFormatConfig:
    """固化后的日志格式化开关结构体"""
    show_time: bool = True
    show_level: bool = True
    show_details: bool = True
    show_thread: bool = True
    show_location: bool = True
    show_module: bool = True


@dataclass
class LogChannelFormats:
    """日志管道格式化配置集，区分常规级别与 RAW 级别"""
    default: LogFinalFormatConfig = field(default_factory=LogFinalFormatConfig)
    raw: LogFinalFormatConfig = field(default_factory=LogFinalFormatConfig)


@dataclass
class LogConsoleRuntimeConfig:
    """控制台管道运行期配置"""
    enable: bool = True
    level: str = "DEBUG"
    use_dim_style: bool = True
    formats: LogChannelFormats = field(default_factory=LogChannelFormats)


@dataclass
class LogFileRuntimeConfig:
    """本地文件管道运行期配置"""
    enable: bool = True
    level: str = "DEBUG"
    path: str = "logs/nvs_app.log"
    size_mb: float = 50.0
    time: str = "00:00"
    retention: str = "7 days"
    compression_format: str = "zip"
    compression_enable: bool = False
    formats: LogChannelFormats = field(default_factory=LogChannelFormats)

# ==============================================================================
# 2. 模块级配置容器（内聚自身的反序列化与多级覆盖逻辑）
# ==============================================================================

@dataclass
class LogModuleRuntimeConfig:
    """日志模块运行期配置顶级容器"""
    console: LogConsoleRuntimeConfig = field(default_factory=LogConsoleRuntimeConfig)
    file: LogFileRuntimeConfig = field(default_factory=LogFileRuntimeConfig)

    @classmethod
    def from_toml_dict(cls, log_toml: dict) -> "LogModuleRuntimeConfig":
        """日志模块专属的解析、打平、覆盖工厂函数"""
        instance = cls()
        
        raw_fmt = log_toml.get("format", {})
        con_toml = log_toml.get("sinks", {}).get("console", {})
        file_toml = log_toml.get("sinks", {}).get("file", {})
        raw_override = log_toml.get("levels", {}).get("RAW", {})

        # --- A. 控制台渠道组装与覆盖 ---
        con_cfg = instance.console
        con_cfg.enable = con_toml.get("enable", True)
        con_cfg.level = con_toml.get("level", "DEBUG")
        con_cfg.use_dim_style = con_toml.get("use_dim_style", True)
        
        con_default_dict = raw_fmt.copy()
        con_default_dict.update(con_toml.get("override", {}))
        con_cfg.formats.default = LogFinalFormatConfig(**con_default_dict)
        
        con_raw_dict = con_default_dict.copy()
        con_raw_dict.update(raw_override)
        con_cfg.formats.raw = LogFinalFormatConfig(**con_raw_dict)

        # --- B. 文件渠道组装、打平与覆盖 ---
        file_cfg = instance.file
        file_cfg.enable = file_toml.get("enable", True)
        file_cfg.level = file_toml.get("level", "DEBUG")
        file_cfg.path = file_toml.get("path", "logs/nvs_app.log")
        file_cfg.size_mb = file_toml.get("rotation", {}).get("size_mb", 50.0)
        file_cfg.time = file_toml.get("rotation", {}).get("time", "00:00")
        file_cfg.retention = file_toml.get("retention", {}).get("rule", "7 days")
        file_cfg.compression_format = file_toml.get("compression", {}).get("format", "zip")
        file_cfg.compression_enable = file_toml.get("compression", {}).get("enable", False)

        file_default_dict = raw_fmt.copy()
        file_default_dict.update(file_toml.get("override", {}))
        file_cfg.formats.default = LogFinalFormatConfig(**file_default_dict)
        
        file_raw_dict = file_default_dict.copy()
        file_raw_dict.update(raw_override)
        file_cfg.formats.raw = LogFinalFormatConfig(**file_raw_dict)

        return instance

    @classmethod
    def create_default_fallback(cls) -> "LogModuleRuntimeConfig":
        """未检测到配置文件时，日志模块自带的硬编码保底覆盖规则"""
        instance = cls()
        instance.console.formats.raw.show_time = False
        instance.console.formats.raw.show_details = False
        instance.file.formats.raw.show_time = False
        instance.file.formats.raw.show_details = False
        return instance

# ==============================================================================
# 3. 全局应用配置根容器
# ==============================================================================

@dataclass
class AppConfig:
    """全局应用配置根容器"""
    log: LogModuleRuntimeConfig = field(default_factory=LogModuleRuntimeConfig)
    # 未来可在此平行扩展其他硬件或算法业务模块：
    # serial: SerialModuleRuntimeConfig = field(default_factory=SerialModuleRuntimeConfig)
    # ocr: OcrModuleRuntimeConfig = field(default_factory=OcrModuleRuntimeConfig)

# ==============================================================================
# 4. 配置管理器（高内聚、模块化组合）
# ==============================================================================

class ConfigManager:
    @staticmethod
    def get_root_dir() -> Path:
        """获取项目物理根目录"""
        return Path(__file__).resolve().parents[2]

    @classmethod
    def load(cls) -> AppConfig:
        """主入口：分发数据片断，组合组装各子模块配置"""
        app_cfg = AppConfig()
        user_path = cls.get_root_dir() / "config" / "config.toml"
        
        # 1. 外部配置文件不存在，各子模块执行各自的保底fallback逻辑
        if not user_path.exists():
            app_cfg.log = LogModuleRuntimeConfig.create_default_fallback()
            # app_cfg.serial = SerialModuleRuntimeConfig.create_default_fallback()
            return app_cfg

        # 2. 外部配置文件存在，读取并分发各模块解析线
        try:
            with open(user_path, "rb") as f:
                toml_root = tomllib.load(f)
                
                # --- 分发组装线 1：日志模块 ---
                log_data = toml_root.get("log", {})
                app_cfg.log = LogModuleRuntimeConfig.from_toml_dict(log_data)
                
                # --- 分发组装线 2：未来串口模块扩展 ---
                # serial_data = toml_root.get("serial", {})
                # app_cfg.serial = SerialModuleRuntimeConfig.from_toml_dict(serial_data)
                
                # --- 分发组装线 3：未来OCR模块扩展 ---
                # ocr_data = toml_root.get("ocr", {})
                # app_cfg.ocr = OcrModuleRuntimeConfig.from_toml_dict(ocr_data)

        except Exception as e:
            sys.stderr.write(f"[Config] 增量覆盖合并计算失败，强行维持出厂默认属性: {e}\n")
            # 异常时同样保障日志模块的出厂保底
            app_cfg.log = LogModuleRuntimeConfig.create_default_fallback()
        
        return app_cfg


cfg = ConfigManager.load()