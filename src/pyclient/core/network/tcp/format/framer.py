import json
from typing import Callable
from .packet import NvsPacket


class StreamFramer:
    """流成帧器：从字节流中切分出完整的 NvsPacket"""

    def __init__(self, on_packet_parsed: Callable[[NvsPacket], None]):
        self._buffer = bytearray()
        self._on_packet_parsed = on_packet_parsed

    def feed(self, data: bytes):
        """喂入网络碎片字节"""
        if not data:
            return
        self._buffer.extend(data)
        self._process_buffer()

    def _process_buffer(self):
        while True:
            first_sep = self._buffer.find(b'-#')
            if first_sep == -1:
                pos = self._buffer.find(b'\r')
                if pos != -1:
                    self._parse_and_emit(self._buffer[:pos])
                    self._buffer = self._buffer[pos + 1:]
                    continue
                break

            cmd_part = self._buffer[:first_sep]
            # 动态二进制长度探测
            if b"File_SVC_Read_Data" in cmd_part:
                second_sep = self._buffer.find(b'-#', first_sep + 2)
                if second_sep == -1:
                    break
                try:
                    json_bytes = self._buffer[first_sep + 2: second_sep]
                    meta = json.loads(json_bytes.decode('utf-8'))
                    data_len = meta.get('data_len', 0)
                    total_len = second_sep + 2 + data_len + 1

                    if len(self._buffer) < total_len:
                        break

                    exact_bin = self._buffer[second_sep +
                                             2: second_sep + 2 + data_len]
                    self._emit_packet(
                        cmd=cmd_part.decode('utf-8', errors='ignore'),
                        payload_str=json_bytes.decode(
                            'utf-8', errors='ignore'),
                        payload_dict=meta,
                        binary_data=exact_bin,
                        raw=self._buffer[:total_len]
                    )
                    self._buffer = self._buffer[total_len:]
                    continue
                except Exception:
                    break
            else:
                pos = self._buffer.find(b'\r')
                if pos == -1:
                    break
                self._parse_and_emit(self._buffer[:pos])
                self._buffer = self._buffer[pos + 1:]

    def _parse_and_emit(self, frame_bytes: bytes):
        raw_str = frame_bytes.decode('utf-8', errors='ignore')
        if raw_str.startswith("ER-#"):
            self._emit_packet("ER", payload_str=raw_str, raw=frame_bytes)
            return

        parts = frame_bytes.split(b"-#", 2)
        cmd = parts[0].decode('utf-8', errors='ignore')
        payload_str = parts[1].decode(
            'utf-8', errors='ignore') if len(parts) >= 2 else ""
        binary = parts[2] if len(parts) == 3 else b''

        payload_dict = {}
        if payload_str and payload_str != "OK":
            try:
                payload_dict = json.loads(payload_str)
            except json.JSONDecodeError:
                pass

        self._emit_packet(cmd, payload_str, payload_dict, binary, frame_bytes)

    def _emit_packet(self, cmd: str, payload_str: str, payload_dict: dict = None, binary_data: bytes = b"", raw: bytes = b""):
        pkt = NvsPacket(cmd, payload_str, payload_dict or {}, binary_data, raw)
        self._on_packet_parsed(pkt)
