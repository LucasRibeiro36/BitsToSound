import pyaudio
import numpy as np

# Configurações para a modulação de frequência
BASE_FREQUENCY = 1000  # Frequência inicial para o byte 0
FREQUENCY_STEP = 10    # Incremento de frequência por byte
SAMPLE_RATE = 48000    # Taxa de amostragem de áudio
DURATION = 0.1        # Duração de cada byte em segundos

def encode_bytes(data):
    """Codifica uma sequência de bytes em uma onda de áudio."""
    samples = []
    for byte in data:
        frequency = BASE_FREQUENCY + byte * FREQUENCY_STEP
        t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
        signal = np.sin(frequency * t * 2 * np.pi)
        samples.extend(signal)
    return np.array(samples, dtype=np.float32)

# Dados de exemplo para transmissão
byte_data = b"oi, tudo bem????\n"

# Codifica os bytes em um sinal de áudio
audio_waveform = encode_bytes(byte_data)

# Configurações de PyAudio para transmissão
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paFloat32, channels=1, rate=SAMPLE_RATE, output=True)

# Transmite o sinal de áudio
print("Transmitting data...")
stream.write(audio_waveform.tobytes())
stream.stop_stream()
stream.close()
p.terminate()
