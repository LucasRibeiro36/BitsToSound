import os
import struct
import time
from pathlib import Path

import numpy as np
import pyaudio

from service.ProtocolLayers import (
    MAX_PAYLOAD_SIZE,
    PROTO_ACK,
    PROTO_CHAT,
    PROTO_FILE_CHUNK,
    PROTO_FILE_END,
    PROTO_FILE_META,
    PROTO_NACK,
    PROTO_PING,
    ProtocolStack,
)
from service.ToneCodec import DecoderState, ToneCodec


class ServerService:
    def __init__(self, node_id: int = 1, destination_id: int = 2):
        self.node_id = node_id
        self.destination_id = destination_id
        self.ttl = 8
        self.protocol = ProtocolStack()
        self.codec = ToneCodec()
        self.next_sequence = 0

    @property
    def sample_rate(self) -> int:
        return self.codec.sample_rate

    def _next_seq(self) -> int:
        seq = self.next_sequence
        self.next_sequence = (self.next_sequence + 1) % 256
        return seq

    def _transmit_frame(self, frame: bytes) -> None:
        audio_waveform = self.codec.encode_bytes(frame)
        if audio_waveform.size == 0:
            return

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            output=True,
        )
        try:
            stream.write(audio_waveform.tobytes())
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    def _listen_frames(self, timeout: float = 1.2):
        frames = []
        byte_buffer = bytearray()
        decoder_state = DecoderState()

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
            while time.time() - started_at < timeout:
                data = stream.read(1024, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.float32)
                decoded = self.codec.decode_samples(samples, decoder_state)
                if not decoded:
                    continue
                byte_buffer.extend(decoded)
                parsed = self.protocol.parse_stream(byte_buffer)
                if parsed:
                    frames.extend(parsed)
                    return frames
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        return frames

    def _wait_for_ack(self, seq: int, timeout: float = 1.2) -> bool:
        frames = self._listen_frames(timeout=timeout)
        for frame in frames:
            if frame.dst not in (self.node_id, 255):
                continue
            if frame.protocol == PROTO_ACK:
                acked_seq = self.protocol.parse_ack_payload(frame.payload)
                if acked_seq == seq:
                    return True
            if frame.protocol == PROTO_NACK:
                acked_seq = self.protocol.parse_ack_payload(frame.payload)
                if acked_seq == seq:
                    return False
        return False

    def send_packet(self, protocol: int, payload: bytes, *, wait_ack: bool = True, retries: int = 3) -> bool:
        fragments = self.protocol.segment_payload(payload, chunk_size=MAX_PAYLOAD_SIZE)

        for fragment, flags in fragments:
            seq = self._next_seq()
            frame = self.protocol.build_frame(
                protocol=protocol,
                flags=flags,
                src=self.node_id,
                dst=self.destination_id,
                ttl=self.ttl,
                seq=seq,
                payload=fragment,
            )

            delivered = False
            for _ in range(retries):
                self._transmit_frame(frame)
                if not wait_ack:
                    delivered = True
                    break
                if self._wait_for_ack(seq):
                    delivered = True
                    break

            if not delivered:
                return False

        return True

    def send_chat(self, text: str) -> bool:
        return self.send_packet(PROTO_CHAT, text.encode("utf-8"), wait_ack=True)

    def send_ping(self, payload: str = "ping") -> bool:
        return self.send_packet(PROTO_PING, payload.encode("utf-8"), wait_ack=True)

    def send_file(self, file_path: str) -> bool:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        data = path.read_bytes()
        transfer_id = int(time.time() * 1000) % 65536

        metadata_payload = self.protocol.build_file_meta(transfer_id=transfer_id, filename=path.name, data=data)
        if not self.send_packet(PROTO_FILE_META, metadata_payload, wait_ack=True):
            return False

        chunk_size = MAX_PAYLOAD_SIZE - 4
        for chunk_index, offset in enumerate(range(0, len(data), chunk_size)):
            chunk = data[offset : offset + chunk_size]
            payload = struct.pack("!HH", transfer_id, chunk_index) + chunk
            if not self.send_packet(PROTO_FILE_CHUNK, payload, wait_ack=True):
                return False

        end_payload = struct.pack("!H", transfer_id)
        return self.send_packet(PROTO_FILE_END, end_payload, wait_ack=True)

    # Backward-compatibility with the old entrypoint.
    def transmit_audio(self, byte_data: bytes) -> None:
        self.send_packet(PROTO_CHAT, byte_data, wait_ack=False)
