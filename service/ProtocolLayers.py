import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


PREAMBLE = b"BTSN"
VERSION = 1

PROTO_CHAT = 1
PROTO_FILE_META = 2
PROTO_FILE_CHUNK = 3
PROTO_FILE_END = 4
PROTO_PING = 5
PROTO_PONG = 6
PROTO_ACK = 250
PROTO_NACK = 251

FLAG_MORE_FRAGMENTS = 0x01

MAX_PAYLOAD_SIZE = 160
HEADER_FORMAT = "!BBBBBBBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
CRC_SIZE = 4


@dataclass
class Frame:
    version: int
    protocol: int
    flags: int
    src: int
    dst: int
    ttl: int
    seq: int
    payload: bytes


class ProtocolStack:
    def build_frame(
        self,
        *,
        protocol: int,
        flags: int,
        src: int,
        dst: int,
        ttl: int,
        seq: int,
        payload: bytes,
    ) -> bytes:
        header = struct.pack(
            HEADER_FORMAT,
            VERSION,
            protocol,
            flags,
            src,
            dst,
            ttl,
            seq,
            len(payload),
        )
        body = PREAMBLE + header + payload
        crc = struct.pack("!I", zlib.crc32(body) & 0xFFFFFFFF)
        return body + crc

    def parse_stream(self, buffer: bytearray) -> List[Frame]:
        frames: List[Frame] = []

        while True:
            preamble_index = buffer.find(PREAMBLE)
            if preamble_index < 0:
                if len(buffer) > len(PREAMBLE):
                    del buffer[:-len(PREAMBLE)]
                return frames

            if preamble_index > 0:
                del buffer[:preamble_index]

            if len(buffer) < len(PREAMBLE) + HEADER_SIZE + CRC_SIZE:
                return frames

            header_start = len(PREAMBLE)
            header_end = header_start + HEADER_SIZE
            header = buffer[header_start:header_end]
            (
                version,
                protocol,
                flags,
                src,
                dst,
                ttl,
                seq,
                payload_length,
            ) = struct.unpack(HEADER_FORMAT, header)

            frame_len = len(PREAMBLE) + HEADER_SIZE + payload_length + CRC_SIZE
            if len(buffer) < frame_len:
                return frames

            body = bytes(buffer[: frame_len - CRC_SIZE])
            expected_crc = struct.unpack("!I", buffer[frame_len - CRC_SIZE : frame_len])[0]
            actual_crc = zlib.crc32(body) & 0xFFFFFFFF

            if actual_crc != expected_crc or version != VERSION:
                del buffer[0]
                continue

            payload = bytes(buffer[header_end : header_end + payload_length])
            frames.append(
                Frame(
                    version=version,
                    protocol=protocol,
                    flags=flags,
                    src=src,
                    dst=dst,
                    ttl=ttl,
                    seq=seq,
                    payload=payload,
                )
            )
            del buffer[:frame_len]

    def make_ack_payload(self, acked_seq: int) -> bytes:
        return struct.pack("!B", acked_seq)

    def parse_ack_payload(self, payload: bytes) -> Optional[int]:
        if len(payload) != 1:
            return None
        return struct.unpack("!B", payload)[0]

    def segment_payload(self, payload: bytes, chunk_size: int = MAX_PAYLOAD_SIZE) -> List[Tuple[bytes, int]]:
        if not payload:
            return [(b"", 0)]

        chunks: List[Tuple[bytes, int]] = []
        for offset in range(0, len(payload), chunk_size):
            fragment = payload[offset : offset + chunk_size]
            flags = FLAG_MORE_FRAGMENTS if offset + chunk_size < len(payload) else 0
            chunks.append((fragment, flags))
        return chunks

    def reassemble_fragments(self, fragments: List[bytes]) -> bytes:
        return b"".join(fragments)

    def build_file_meta(self, transfer_id: int, filename: str, data: bytes) -> bytes:
        digest = hashlib.sha256(data).hexdigest()
        payload = {
            "transfer_id": transfer_id,
            "filename": filename,
            "size": len(data),
            "sha256": digest,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def parse_file_meta(self, payload: bytes) -> Dict[str, object]:
        return json.loads(payload.decode("utf-8"))
