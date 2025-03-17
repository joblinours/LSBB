import socket, struct, threading, cv2, numpy as np, tkinter as tk, time, queue
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import sounddevice as sd
from cryptography.fernet import Fernet

# === Configuration chiffrement ===
SHARED_KEY = b'59oGVs16nJwv-s6k4kBDuUcMIhSJcZ0PQRSdg1k9Ioo='  # exemple
fernet = Fernet(SHARED_KEY)

# === Paramètres réseau ===
VIDEO_PORT = 8000
AUDIO_PORT = 8001
COMMAND_PORT = 8002  # Nouveau port pour les commandes
HOST = ''  # écoute sur toutes les interfaces

# === Configuration audio ===
AUDIO_RATE = 44100  # Taux d'échantillonnage audio
AUDIO_CHUNK = 1024  # Taille du chunk audio
CHANNELS = 1         # Nombre de canaux audio (1 = mono, 2 = stéréo)
dtype = 'int16'      # Type de données audio

# === Structures globales ===
cameras = {}
audio_queues = {}
cameras_lock = threading.Lock()
selected_camera = None
recording = False
video_recorder = None
zoom_active = False
audio_muted = False
current_frame = None

# Variables pour le drag & drop du zoom
zoom_offset_x = 0
zoom_offset_y = 0
is_dragging = False
start_x = 0
start_y = 0

# === Gestion des connexions vidéo ===
def client_handler_video(conn, addr):
    global cameras
    data_buffer = b''
    payload_size = struct.calcsize("!I")
    default_name = None
    try:
        while len(data_buffer) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                return
            data_buffer += packet
        name_size = struct.unpack("!I", data_buffer[:payload_size])[0]
        data_buffer = data_buffer[payload_size:]
        while len(data_buffer) < name_size:
            packet = conn.recv(4096)
            if not packet:
                return
            data_buffer += packet
        encrypted_name = data_buffer[:name_size]
        data_buffer = data_buffer[name_size:]
        try:
            default_name = fernet.decrypt(encrypted_name).decode()
        except Exception as e:
            print("Erreur de déchiffrement du nom de caméra :", e)
            return

        with cameras_lock:
            if default_name not in cameras:
                cameras[default_name] = {
                    'name': default_name,
                    'queue': queue.Queue(),
                    'online': True,
                    'last_update': time.time(),
                    'addr': addr  # Ajout de l'adresse pour les commandes
                }
            else:
                cameras[default_name]['online'] = True
                cameras[default_name]['last_update'] = time.time()
                while not cameras[default_name]['queue'].empty():
                    try:
                        cameras[default_name]['queue'].get_nowait()
                    except:
                        break
        print(f"Caméra '{default_name}' connectée depuis {addr}")

        while True:
            while len(data_buffer) < payload_size:
                packet = conn.recv(4096)
                if not packet:
                    raise Exception("Connexion fermée")
                data_buffer += packet
            frame_size = struct.unpack("!I", data_buffer[:payload_size])[0]
            data_buffer = data_buffer[payload_size:]
            while len(data_buffer) < frame_size:
                packet = conn.recv(4096)
                if not packet:
                    raise Exception("Connexion fermée")
                data_buffer += packet
            encrypted_frame = data_buffer[:frame_size]
            data_buffer = data_buffer[frame_size:]
            try:
                frame_data = fernet.decrypt(encrypted_frame)
            except Exception as e:
                print("Erreur de déchiffrement (vidéo) :", e)
                continue
            np_arr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is not None:
                with cameras_lock:
                    if default_name in cameras:
                        while not cameras[default_name]['queue'].empty():
                            try:
                                cameras[default_name]['queue'].get_nowait()
                            except:
                                break
                        cameras[default_name]['queue'].put(frame)
                        cameras[default_name]['last_update'] = time.time()
    except Exception as e:
        print("Erreur vidéo avec", addr, ":", e)
    finally:
        with cameras_lock:
            if default_name in cameras:
                cameras[default_name]['online'] = False
        conn.close()
        print(f"Caméra '{default_name}' déconnectée")

# === Gestion des connexions audio ===
def client_handler_audio(conn, addr):
    global audio_queues
    data_buffer = b""
    payload_size = struct.calcsize("!I")
    default_name = None
    try:
        while len(data_buffer) < payload_size:
            packet = conn.recv(4096)
            if not packet:
                return
            data_buffer += packet
        name_size = struct.unpack("!I", data_buffer[:payload_size])[0]
        data_buffer = data_buffer[payload_size:]
        while len(data_buffer) < name_size:
            packet = conn.recv(4096)
            if not packet:
                return
            data_buffer += packet
        encrypted_name = data_buffer[:name_size]
        data_buffer = data_buffer[name_size:]
        try:
            default_name = fernet.decrypt(encrypted_name).decode()
        except Exception as e:
            print("Erreur de déchiffrement du nom (audio) :", e)
            return

        with cameras_lock:
            if default_name not in audio_queues:
                audio_queues[default_name] = queue.Queue()

        print(f"Audio de la caméra '{default_name}' connectée depuis {addr}")

        while True:
            while len(data_buffer) < payload_size:
                packet = conn.recv(4096)
                if not packet:
                    raise Exception("Connexion fermée")
                data_buffer += packet
            encrypted_size = struct.unpack("!I", data_buffer[:payload_size])[0]
            data_buffer = data_buffer[payload_size:]
            while len(data_buffer) < encrypted_size:
                packet = conn.recv(4096)
                if not packet:
                    raise Exception("Connexion fermée")
                data_buffer += packet
            encrypted_audio = data_buffer[:encrypted_size]
            data_buffer = data_buffer[encrypted_size:]
            try:
                decrypted_audio = fernet.decrypt(encrypted_audio)
            except Exception as e:
                print("Erreur de déchiffrement (audio) :", e)
                continue
            with cameras_lock:
                if default_name in audio_queues:
                    while not audio_queues[default_name].empty():
                        try:
                            audio_queues[default_name].get_nowait()
                        except:
                            break
                    audio_queues[default_name].put(decrypted_audio)
    except Exception as e:
        print("Erreur audio avec", addr, ":", e)
    finally:
        conn.close()
        print(f"Audio de la caméra '{default_name}' déconnecté")

# === Lecture audio ===
def audio_playback():
    try:
        with sd.RawOutputStream(samplerate=AUDIO_RATE, blocksize=AUDIO_CHUNK, channels=CHANNELS, dtype=dtype) as stream:
            while True:
                if selected_camera is not None:
                    with cameras_lock:
                        aq = audio_queues.get(selected_camera)
                    if aq and not aq.empty():
                        chunk = None
                        while not aq.empty():
                            try:
                                chunk = aq.get_nowait()
                            except queue.Empty:
                                break
                        if chunk and not audio_muted:
                            stream.write(chunk)
                        else:
                            sd.sleep(5)
                    else:
                        sd.sleep(5)
                else:
                    sd.sleep(20)
    except Exception as e:
        print("Erreur dans la lecture audio :", e)

# === Serveurs ===
def start_video_server():
    video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    video_sock.bind((HOST, VIDEO_PORT))
    video_sock.listen(5)
    print("Serveur vidéo en écoute sur le port", VIDEO_PORT)
    while True:
        conn, addr = video_sock.accept()
        threading.Thread(target=client_handler_video, args=(conn, addr), daemon=True).start()

def start_audio_server():
    audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    audio_sock.bind((HOST, AUDIO_PORT))
    audio_sock.listen(5)
    print("Serveur audio en écoute sur le port", AUDIO_PORT)
    while True:
        conn, addr = audio_sock.accept()
        threading.Thread(target=client_handler_audio, args=(conn, addr), daemon=True).start()

# === Gestion du drag & drop ===
def start_drag(event):
    global is_dragging, start_x, start_y
    if zoom_active:
        is_dragging = True
        start_x = event.x
        start_y = event.y

def during_drag(event):
    global zoom_offset_x, zoom_offset_y, start_x, start_y
    if zoom_active and is_dragging:
        dx = event.x - start_x
        dy = event.y - start_y
        zoom_offset_x += dx * 0.5
        zoom_offset_y += dy * 0.5
        start_x = event.x
        start_y = event.y

def end_drag(event):
    global is_dragging
    is_dragging = False

# === Interface graphique ===
root = tk.Tk()
root.title("Like Stalk but better - LSBB")

# Cadre gauche
list_frame = tk.Frame(root)
list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
camera_listbox = tk.Listbox(list_frame, width=40)
camera_listbox.pack(side=tk.TOP, fill=tk.Y)
rename_button = tk.Button(list_frame, text="Renommer", width=15)
rename_button.pack(pady=5)

# Cadre droit
display_frame = tk.Frame(root)
display_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
video_label = tk.Label(display_frame)
video_label.pack()
video_label.bind("<ButtonPress-1>", start_drag)
video_label.bind("<B1-Motion>", during_drag)
video_label.bind("<ButtonRelease-1>", end_drag)

# Contrôles
controls_frame = tk.Frame(display_frame)
controls_frame.pack(pady=5)
record_button = tk.Button(controls_frame, text="Start Recording", width=15)
record_button.grid(row=0, column=0, padx=3)
screenshot_button = tk.Button(controls_frame, text="Screenshot", width=15)
screenshot_button.grid(row=0, column=1, padx=3)
zoom_button = tk.Button(controls_frame, text="Zoom In", width=15)
zoom_button.grid(row=0, column=2, padx=3)
mute_button = tk.Button(controls_frame, text="Mute", width=15)
mute_button.grid(row=0, column=3, padx=3)
switch_button = tk.Button(controls_frame, text="Switch Source", width=15)  # Nouveau bouton
switch_button.grid(row=0, column=4, padx=3)

# Fonctions UI
def update_camera_list():
    camera_listbox.delete(0, tk.END)
    with cameras_lock:
        for cam_id, cam_data in cameras.items():
            status = "Online" if cam_data['online'] else "Offline"
            display_name = cam_data['name']
            camera_listbox.insert(tk.END, f"{cam_id} - {display_name} ({status})")
    root.after(1000, update_camera_list)

def on_camera_select(event):
    global selected_camera, zoom_offset_x, zoom_offset_y
    selection = camera_listbox.curselection()
    if selection:
        index = selection[0]
        entry = camera_listbox.get(index)
        parts = entry.split(" - ")
        if parts:
            selected_camera = parts[0]
            zoom_offset_x = 0
            zoom_offset_y = 0

def rename_camera():
    global cameras
    if selected_camera is None:
        messagebox.showwarning("Avertissement", "Aucune caméra sélectionnée.")
        return
    new_name = simpledialog.askstring("Renommer la caméra", "Entrez le nouveau nom:")
    if new_name:
        with cameras_lock:
            if selected_camera in cameras:
                cameras[selected_camera]['name'] = new_name

def toggle_recording():
    global recording, video_recorder, current_frame
    if not recording:
        if current_frame is None:
            messagebox.showwarning("Avertissement", "Aucune image disponible pour démarrer l'enregistrement.")
            return
        recording = True
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        filename = time.strftime("recording_%Y%m%d_%H%M%S.avi")
        h, w, _ = current_frame.shape
        video_recorder = cv2.VideoWriter(filename, fourcc, 20.0, (w, h))
        record_button.config(text="Stop Recording")
        print("Enregistrement démarré :", filename)
    else:
        recording = False
        if video_recorder is not None:
            video_recorder.release()
            video_recorder = None
        record_button.config(text="Start Recording")
        print("Enregistrement arrêté.")

def take_screenshot():
    if current_frame is not None:
        filename = time.strftime("screenshot_%Y%m%d_%H%M%S.png")
        cv2.imwrite(filename, current_frame)
        print("Screenshot sauvegardé :", filename)
    else:
        messagebox.showwarning("Avertissement", "Aucune image à sauvegarder.")

def toggle_zoom():
    global zoom_active, zoom_offset_x, zoom_offset_y
    zoom_active = not zoom_active
    if not zoom_active:
        zoom_offset_x = 0
        zoom_offset_y = 0
    zoom_button.config(text="Zoom Out" if zoom_active else "Zoom In")

def toggle_mute():
    global audio_muted
    audio_muted = not audio_muted
    mute_button.config(text="Unmute" if audio_muted else "Mute")
    print("Audio muet." if audio_muted else "Audio activé.")

def toggle_source():
    if selected_camera is None:
        messagebox.showwarning("Avertissement", "Aucune caméra sélectionnée.")
        return
    with cameras_lock:
        cam_data = cameras.get(selected_camera)
        if not cam_data or not cam_data['online']:
            return
        client_ip = cam_data['addr'][0]  # Adresse IP du client

    try:
        cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd_sock.connect((client_ip, COMMAND_PORT))
        cmd_sock.sendall(b'toggle_source')
        cmd_sock.close()
    except Exception as e:
        messagebox.showerror("Erreur", f"Impossible de switcher : {e}")

# Configuration des événements
camera_listbox.bind("<<ListboxSelect>>", on_camera_select)
rename_button.config(command=rename_camera)
record_button.config(command=toggle_recording)
screenshot_button.config(command=take_screenshot)
zoom_button.config(command=toggle_zoom)
mute_button.config(command=toggle_mute)
switch_button.config(command=toggle_source)  # Lier le nouveau bouton

# Lancement des threads
threading.Thread(target=start_video_server, daemon=True).start()
threading.Thread(target=start_audio_server, daemon=True).start()
threading.Thread(target=audio_playback, daemon=True).start()

# Fonction pour mettre à jour l'affichage vidéo
def update_frame():
    global current_frame, video_recorder
    if selected_camera is not None:
        with cameras_lock:
            cam_data = cameras.get(selected_camera)
        if cam_data and cam_data['online']:
            try:
                frame = None
                while not cam_data['queue'].empty():
                    try:
                        frame = cam_data['queue'].get_nowait()
                    except:
                        break
                if frame is not None:
                    current_frame = frame.copy()
                    if zoom_active:
                        h, w, _ = frame.shape
                        original_center_x = w // 2
                        original_center_y = h // 2
                        center_x = original_center_x + int(zoom_offset_x)
                        center_y = original_center_y + int(zoom_offset_y)
                        rx = w // 4
                        ry = h // 4
                        center_x = max(rx, min(w - rx, center_x))
                        center_y = max(ry, min(h - ry, center_y))
                        frame = frame[center_y - ry:center_y + ry, center_x - rx:center_x + rx]
                        frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
                    cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(cv2image)
                    imgtk = ImageTk.PhotoImage(image=pil_image)
                    video_label.imgtk = imgtk
                    video_label.config(image=imgtk)
                    if recording and video_recorder is not None:
                        video_recorder.write(current_frame)
            except Exception as e:
                print("Erreur lors de l'actualisation de l'image :", e)
    root.after(10, update_frame)

# Mise à jour de la liste des caméras et de l'affichage vidéo
update_camera_list()
update_frame()
root.mainloop()