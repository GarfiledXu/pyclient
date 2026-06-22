from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class NvsPacket:
    """协议格式抽象：物理数据帧在内存中的最终形态"""
    cmd: str
    payload_str: str = ""
    payload_dict: Dict[str, Any] = field(default_factory=dict)
    binary_data: bytes = b""
    raw_bytes: bytes = b""

    @property
    def is_error(self) -> bool:
        return self.cmd == "ER"
