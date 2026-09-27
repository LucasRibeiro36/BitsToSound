from dataclasses import dataclass, field
from typing import List

import numpy as np
from scipy.fft import rfft, rfftfreq


@dataclass
class DecoderState:
    sample_remainder: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    pending_nibble: int | None = None


class ToneCodec:
    def __init__(
        self,
        *,
        sample_rate: int = 48_000,
        symbol_duration: float = 0.02,
        base_frequency: int = 1200,
        frequency_step: int = 90,
    ):
        self.sample_rate = sample_rate
        self.symbol_duration = symbol_duration
        self.base_frequency = base_frequency
        self.frequency_step = frequency_step
        self.symbol_samples = int(sample_rate * symbol_duration)
        self._window = np.hanning(self.symbol_samples)

    def encode_bytes(self, data: bytes) -> np.ndarray:
        symbols: List[int] = []
        for byte in data:
            symbols.append((byte >> 4) & 0x0F)
            symbols.append(byte & 0x0F)

        if not symbols:
            return np.array([], dtype=np.float32)

        chunks = []
        for symbol in symbols:
            frequency = self.base_frequency + symbol * self.frequency_step
            t = np.linspace(0, self.symbol_duration, self.symbol_samples, endpoint=False)
            waveform = np.sin(2 * np.pi * frequency * t).astype(np.float32)
            chunks.append(waveform)

        silence = np.zeros(self.symbol_samples // 2, dtype=np.float32)
        return np.concatenate([silence, *chunks, silence])

    def decode_samples(self, samples: np.ndarray, state: DecoderState) -> bytes:
        if state.sample_remainder.size:
            samples = np.concatenate([state.sample_remainder, samples])

        symbols: List[int] = []
        cursor = 0
        while cursor + self.symbol_samples <= len(samples):
            segment = samples[cursor : cursor + self.symbol_samples]
            segment = segment * self._window

            spectrum = np.abs(rfft(segment))
            freqs = rfftfreq(len(segment), 1 / self.sample_rate)
            peak_idx = int(np.argmax(spectrum))
            peak_frequency = freqs[peak_idx]

            symbol = int(round((peak_frequency - self.base_frequency) / self.frequency_step))
            symbol = max(0, min(15, symbol))
            symbols.append(symbol)

            cursor += self.symbol_samples

        state.sample_remainder = samples[cursor:].astype(np.float32, copy=False)

        output = bytearray()
        for symbol in symbols:
            if state.pending_nibble is None:
                state.pending_nibble = symbol
                continue
            output.append((state.pending_nibble << 4) | symbol)
            state.pending_nibble = None

        return bytes(output)
