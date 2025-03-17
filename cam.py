import cv2
import socket
import struct
import threading
import time
from cryptography.fernet import Fernet
import sounddevice as sd
import mss  # Nouvelle importation
import numpy as np  # Nouvelle importation

# Clé symétrique partagée (générée une fois avec Fernet.generate_key())
SHARED_KEY = b'59oGVs16nJwv-s6k4kBDuUcMIhSJcZ0PQRSdg1k9Ioo='  # exemple
fernet = Fernet(SHARED_KEY)

SERVER_IP = '192.168.0.116'  # à modifier selon votre configuration
VIDEO_PORT = 8000
AUDIO_PORT = 8001
COMMAND_PORT = 8002  # Nouveau port pour les commandes

# Variable pour basculer entre écran et webcam
use_screen = False
use_screen_lock = threading.Lock()

def send_video():
    camera_name = socket.gethostname()  # nom par défaut de la machine
    target_fps = 24
    frame_interval = 1 / target_fps

    while True:
        try:
            video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            video_sock.connect((SERVER_IP, VIDEO_PORT))

            # Envoi de l'en-tête : nom de la caméra chiffré
            name_bytes = camera_name.encode()
            encrypted_name = fernet.encrypt(name_bytes)
            video_sock.sendall(struct.pack("!I", len(encrypted_name)) + encrypted_name)

            # Initialisation de la capture (webcam ou écran)
            if use_screen:
                sct = mss.mss()  # Capture d'écran
                monitor = sct.monitors[1]  # Premier moniteur
            else:
                cap = cv2.VideoCapture(0)  # Webcam
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

            while True:
                start_time = time.time()

                # Capture d'écran ou webcam
                if use_screen:
                    frame = np.array(sct.grab(monitor))  # Capture d'écran
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)  # Conversion de couleur
                else:
                    ret, frame = cap.read()  # Webcam
                    if not ret:
                        break

                # Encodage en JPEG avec une qualité modérée
                result, imgencode = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                data = imgencode.tobytes()
                encrypted_data = fernet.encrypt(data)
                packet = struct.pack("!I", len(encrypted_data)) + encrypted_data
                video_sock.sendall(packet)

                # Limitation à environ 24 FPS
                elapsed = time.time() - start_time
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as e:
            time.sleep(2)  # Attente avant reconnexion
        finally:
            try:
                video_sock.close()
                if use_screen:
                    sct.close()  # Fermer la capture d'écran
                else:
                    cap.release()  # Fermer la webcam
            except:
                pass

def send_audio():
    camera_name = socket.gethostname()
    CHUNK = 1024
    AUDIO_RATE = 44100
    CHANNELS = 1
    dtype = 'int16'
    while True:
        try:
            audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            audio_sock.connect((SERVER_IP, AUDIO_PORT))

            # Envoi de l'en-tête : nom de la caméra chiffré
            name_bytes = camera_name.encode()
            encrypted_name = fernet.encrypt(name_bytes)
            audio_sock.sendall(struct.pack("!I", len(encrypted_name)) + encrypted_name)

            with sd.RawInputStream(samplerate=AUDIO_RATE, blocksize=CHUNK, channels=CHANNELS, dtype=dtype) as stream:
                while True:
                    data, overflow = stream.read(CHUNK)
                    audio_data = bytes(data)
                    encrypted_audio = fernet.encrypt(audio_data)
                    packet = struct.pack("!I", len(encrypted_audio)) + encrypted_audio
                    audio_sock.sendall(packet)
        except Exception as e:
            time.sleep(2)
        finally:
            try:
                audio_sock.close()
            except:
                pass

# Serveur de commandes pour basculer entre écran et webcam
def command_server():
    global use_screen
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('0.0.0.0', COMMAND_PORT))
        sock.listen(1)
        while True:
            conn, addr = sock.accept()
            data = conn.recv(1024).decode()
            if data == 'toggle_source':
                with use_screen_lock:
                    use_screen = not use_screen
            conn.close()

if __name__ == '__main__':
    # Démarrer les threads
    threading.Thread(target=command_server, daemon=True).start()
    threading.Thread(target=send_video, daemon=True).start()
    threading.Thread(target=send_audio, daemon=True).start()
    
    # Maintenir le programme actif
    while True:
        time.sleep(1)