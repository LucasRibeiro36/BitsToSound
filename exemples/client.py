import pyaudio
import numpy as np
from scipy.fft import fft

# Configurações para a modulação de frequência
BASE_FREQUENCY = 1000  # Frequência inicial para o byte 0
FREQUENCY_STEP = 10    # Incremento de frequência por byte
SAMPLE_RATE = 48000    # Taxa de amostragem de áudio
DURATION = 0.1        # Duração de cada byte em segundos

def decode_bytes(audio_data):
    """Decodifica uma onda de áudio em uma sequência de bytes."""
    byte_data = []
    n = int(SAMPLE_RATE * DURATION)  # Número de amostras por byte
    num_bytes = len(audio_data) // n

    for i in range(num_bytes):
        segment = audio_data[i*n:(i+1)*n]
        yf = fft(segment)
        xf = np.fft.fftfreq(len(yf), 1 / SAMPLE_RATE)
        idx = np.argmax(np.abs(yf))
        frequency = abs(xf[idx])

        # Mapeia a frequência detectada de volta para o byte
        byte = int((frequency - BASE_FREQUENCY) / FREQUENCY_STEP)
        # Garante que o valor do byte está no intervalo de 0 a 255
        if 0 <= byte <= 255:
            byte_data.append(byte)
        else:
            pass

    return bytes(byte_data)

# Configurações de PyAudio para recepção
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paFloat32, channels=1, rate=SAMPLE_RATE, input=True, frames_per_buffer=1024)

print("Listening for data... Press Ctrl+C to stop.")
audio_buffer = []
decoded_buffer = ""

try:
    while True:
        data = stream.read(1024)
        audio_buffer.extend(np.frombuffer(data, dtype=np.float32))
        
        # Decodificar o áudio se o buffer atingir o tamanho necessário
        if len(audio_buffer) >= int(SAMPLE_RATE * DURATION):
            decoded_bytes = decode_bytes(np.array(audio_buffer[:int(SAMPLE_RATE * DURATION)]))
            audio_buffer = audio_buffer[int(SAMPLE_RATE * DURATION):]  # Limpar o buffer processado
            
            try:
                decoded_buffer += decoded_bytes.decode("utf-8")
                if decoded_bytes.endswith(b"\n"):
                    print("Decoded message:", decoded_buffer.strip())
                    decoded_buffer = ""
            except UnicodeDecodeError:
                print("Failed to decode some bytes. Skipping...")
except KeyboardInterrupt:
    pass

stream.stop_stream()
stream.close()
p.terminate()
