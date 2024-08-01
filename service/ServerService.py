import pyaudio
import numpy as np

class ServerService:
    def __init__(self):
        self.BASE_FREQUENCY = 1000
        self.FREQUENCY_STEP = 10
        self.SAMPLE_RATE = 48000
        self.DURATION = 0.1
        
    DURATION = 0.1

    def encode_bytes(self, data):
        samples = []
        message = b"Addr: 192.168.0.1\n"
        message += b"\n"
        message += data + b"\n"
        
        # Codificação dos bytes em frequências
        for byte in message:
            frequency = self.BASE_FREQUENCY + byte * self.FREQUENCY_STEP
            t = np.linspace(0, self.DURATION, int(self.SAMPLE_RATE * self.DURATION), False)
            signal = np.sin(frequency * t * 2 * np.pi)
            samples.extend(signal)
        
        return np.array(samples, dtype=np.float32)

    def transmit_audio(self, byte_data):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paFloat32, channels=1, rate=self.SAMPLE_RATE, output=True)

        audio_waveform = self.encode_bytes(byte_data)
        stream.write(audio_waveform.tobytes())

        stream.stop_stream()
        stream.close()
        p.terminate()

