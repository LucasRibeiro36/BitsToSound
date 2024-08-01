from scipy.fft import fft
import pyaudio
import numpy as np

class ClientService:
    BASE_FREQUENCY = 1000
    FREQUENCY_STEP = 10
    SAMPLE_RATE = 48000
    DURATION = 0.1

    def decode_bytes(self, audio_data):
        byte_data = []
        n = int(self.SAMPLE_RATE * self.DURATION)
        num_bytes = len(audio_data) // n

        for i in range(num_bytes):
            segment = audio_data[i*n:(i+1)*n]
            yf = fft(segment)
            xf = np.fft.fftfreq(len(yf), 1 / self.SAMPLE_RATE)
            idx = np.argmax(np.abs(yf))
            frequency = abs(xf[idx])

            byte = int((frequency - self.BASE_FREQUENCY) / self.FREQUENCY_STEP)
            if 0 <= byte <= 255:
                byte_data.append(byte)

        return bytes(byte_data)

    def receive_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paFloat32, channels=1, rate=self.SAMPLE_RATE, input=True, frames_per_buffer=1024)

        audio_buffer = []
        decoded_buffer = ""
        print("Listening for data...")

        try:
            while True:
                data = stream.read(1024)
                audio_buffer.extend(np.frombuffer(data, dtype=np.float32))

                if len(audio_buffer) >= int(self.SAMPLE_RATE * self.DURATION):
                    decoded_bytes = self.decode_bytes(np.array(audio_buffer[:int(self.SAMPLE_RATE * self.DURATION)]))
                    audio_buffer = audio_buffer[int(self.SAMPLE_RATE * self.DURATION):]

                    try:
                        decoded_text = decoded_bytes.decode("utf-8", errors="ignore")
                        decoded_buffer += decoded_text
                        if decoded_bytes.endswith(b"\n"):
                            break
                    except UnicodeDecodeError:
                        print("Failed to decode some bytes. Skipping...")
        
        except KeyboardInterrupt:
            print("Interrupted by user.")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
        
        return decoded_buffer.strip()


