import json
import struct
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyaudio

from service.ProtocolLayers import (
    PROTO_ACK,
    PROTO_CHAT,
    PROTO_FILE_CHUNK,
    PROTO_FILE_END,
    PROTO_FILE_META,
    PROTO_NACK,
    PROTO_PING,
    PROTO_PONG,
    Frame,
    ProtocolStack,
)
from service.ToneCodec import DecoderState, ToneCodec


class ClientService:
    def __init__(self, node_id: int = 2, destination_id: int = 1):
        self.node_id = node_id
        self.destination_id = destination_id
        self.ttl = 8
        self.protocol = ProtocolStack()
        self.codec = ToneCodec()
        self.next_sequence = 0
        self.byte_buffer = bytearray()
        self.decoder_state = DecoderState()
        self.fragment_buffers: Dict[Tuple[int, int], List[bytes]] = {}
        self.file_sessions: Dict[int, Dict[str, object]] = {}

    @property
    def sample_rate(self) -> int:
        return self.codec.sample_rate

    def _next_seq(self) -> int:
        seq = self.next_sequence
        self.next_sequence = (self.next_sequence + 1) % 256
        return seq

    def _transmit_frame(self, frame: bytes) -> None:
        waveform = self.codec.encode_bytes(frame)
        if waveform.size == 0:
            return

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            output=True,
        )
        try:
            stream.write(waveform.tobytes())
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    def _send_control(self, *, protocol: int, dst: int, acked_seq: int) -> None:
        payload = self.protocol.make_ack_payload(acked_seq)
        frame = self.protocol.build_frame(
            protocol=protocol,
            flags=0,
            src=self.node_id,
            dst=dst,
            ttl=self.ttl,
            seq=self._next_seq(),
            payload=payload,
        )
        self._transmit_frame(frame)

    def _send_ack(self, dst: int, acked_seq: int) -> None:
        self._send_control(protocol=PROTO_ACK, dst=dst, acked_seq=acked_seq)

    def _send_nack(self, dst: int, acked_seq: int) -> None:
        self._send_control(protocol=PROTO_NACK, dst=dst, acked_seq=acked_seq)

    def _send_pong(self, dst: int, payload: bytes) -> None:
        frame = self.protocol.build_frame(
            protocol=PROTO_PONG,
            flags=0,
            src=self.node_id,
            dst=dst,
            ttl=self.ttl,
            seq=self._next_seq(),
            payload=payload,
        )
        self._transmit_frame(frame)

    def _read_frames(self, stream) -> List[Frame]:
        data = stream.read(1024, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.float32)
        decoded = self.codec.decode_samples(samples, self.decoder_state)
        if decoded:
            self.byte_buffer.extend(decoded)
        return self.protocol.parse_stream(self.byte_buffer)

    def _reassemble_payload(self, frame: Frame) -> Optional[bytes]:
        key = (frame.src, frame.protocol)
        fragments = self.fragment_buffers.setdefault(key, [])
        fragments.append(frame.payload)

        if frame.flags & 0x01:
            return None

        payload = self.protocol.reassemble_fragments(fragments)
        self.fragment_buffers.pop(key, None)
        return payload

    def _handle_file_packet(self, frame: Frame, payload: bytes) -> Optional[Dict[str, str]]:
        if frame.protocol == PROTO_FILE_META:
            metadata = self.protocol.parse_file_meta(payload)
            transfer_id = int(metadata["transfer_id"])
            self.file_sessions[transfer_id] = {
                "meta": metadata,
                "chunks": {},
            }
            return {
                "type": "file_meta",
                "transfer_id": str(transfer_id),
                "filename": str(metadata["filename"]),
            }

        if frame.protocol == PROTO_FILE_CHUNK:
            if len(payload) < 4:
                return None
            transfer_id, chunk_index = struct.unpack("!HH", payload[:4])
            session = self.file_sessions.get(transfer_id)
            if session is None:
                return None
            session["chunks"][chunk_index] = payload[4:]
            return None

        if frame.protocol == PROTO_FILE_END:
            if len(payload) < 2:
                return None
            transfer_id = struct.unpack("!H", payload[:2])[0]
            session = self.file_sessions.pop(transfer_id, None)
            if session is None:
                return None

            metadata = session["meta"]
            chunks = session["chunks"]
            ordered_data = b"".join(chunks[idx] for idx in sorted(chunks))

            expected_size = int(metadata["size"])
            expected_hash = str(metadata["sha256"])
            if len(ordered_data) != expected_size:
                return {
                    "type": "file_error",
                    "filename": str(metadata["filename"]),
                    "reason": "size mismatch",
                }

            import hashlib

            current_hash = hashlib.sha256(ordered_data).hexdigest()
            if current_hash != expected_hash:
                return {
                    "type": "file_error",
                    "filename": str(metadata["filename"]),
                    "reason": "hash mismatch",
                }

            downloads_dir = Path("/home/runner/work/BitsToSound/BitsToSound/downloads")
            downloads_dir.mkdir(parents=True, exist_ok=True)
            output_path = downloads_dir / str(metadata["filename"])
            output_path.write_bytes(ordered_data)

            return {
                "type": "file_saved",
                "filename": str(output_path),
            }

        return None

    def receive_event(self, timeout_seconds: Optional[float] = None) -> Optional[Dict[str, str]]:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=1024,
        )

        started_at = time.time()
        try:
            while True:
                frames = self._read_frames(stream)
                for frame in frames:
                    if frame.dst not in (self.node_id, 255):
                        continue

                    if frame.protocol not in (PROTO_ACK, PROTO_NACK):
                        self._send_ack(dst=frame.src, acked_seq=frame.seq)

                    payload = self._reassemble_payload(frame)
                    if payload is None:
                        continue

                    if frame.protocol == PROTO_CHAT:
                        text = payload.decode("utf-8", errors="replace")
                        return {"type": "chat", "text": text, "src": str(frame.src)}

                    if frame.protocol == PROTO_PING:
                        self._send_pong(dst=frame.src, payload=payload)
                        text = payload.decode("utf-8", errors="replace")
                        return {"type": "ping", "text": text, "src": str(frame.src)}

                    if frame.protocol == PROTO_PONG:
                        text = payload.decode("utf-8", errors="replace")
                        return {"type": "pong", "text": text, "src": str(frame.src)}

                    if frame.protocol in (PROTO_FILE_META, PROTO_FILE_CHUNK, PROTO_FILE_END):
                        file_event = self._handle_file_packet(frame, payload)
                        if file_event is not None:
                            return file_event

                if timeout_seconds is not None and (time.time() - started_at) >= timeout_seconds:
                    return None
        except Exception:
            self._send_nack(dst=self.destination_id, acked_seq=0)
            raise
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    # Backward-compatibility with the old entrypoint.
    def receive_audio(self):
        event = self.receive_event(timeout_seconds=None)
        if event is None:
            return ""
        if event.get("type") == "chat":
            return event.get("text", "")
        return json.dumps(event, ensure_ascii=False)
