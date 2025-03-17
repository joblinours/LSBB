#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox, simpledialog
import socket, struct, cv2, numpy as np, time, threading
from PIL import Image, ImageTk

# === Configuration ===
SERVER_IP    = '192.168.0.249'  # À modifier avec l'adresse IP de votre serveur central
VISU_PORT    = 8003           # Port pour récupérer le flux vidéo
LIST_PORT    = 8004           # Port pour récupérer la liste des caméras (nom;ip;source)
COMMAND_PORT = 8002           # Port pour envoyer les commandes (inclut les événements souris)

class Visualiseur:
    def __init__(self, master):
        self.master = master
        master.title("Visualisateur Complet")
        
        self.selected_camera = None
        self.selected_camera_ip = None
        self.selected_camera_source = None
        self.zoom_active = False
        self.zoom_offset_x = 0
        self.zoom_offset_y = 0
        self.current_frame = None
        self.recording = False
        self.video_recorder = None
        self.is_dragging = False
        self.start_x = 0
        self.start_y = 0
        self.interactive_mode = False
        
        # Pour conserver un renommage local (clé = nom d'origine)
        self.camera_display_names = {}
        self.cam_list = []  # Liste des tuples (nom, ip, source)
        
        # --- Cadre gauche : liste des caméras et bouton de renommage ---
        self.list_frame = tk.Frame(master)
        self.list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        self.camera_listbox = tk.Listbox(self.list_frame, width=40)
        self.camera_listbox.pack(side=tk.TOP, fill=tk.Y)
        self.rename_button = tk.Button(self.list_frame, text="Renommer", command=self.rename_camera)
        self.rename_button.pack(pady=5)
        
        # --- Cadre droit : affichage vidéo et contrôles ---
        self.display_frame = tk.Frame(master)
        self.display_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.video_label = tk.Label(self.display_frame)
        self.video_label.pack()
        self.video_label.bind("<ButtonPress-1>", self.start_drag)
        self.video_label.bind("<B1-Motion>", self.during_drag)
        self.video_label.bind("<ButtonRelease-1>", self.end_drag)
        
        self.controls_frame = tk.Frame(self.display_frame)
        self.controls_frame.pack(pady=5)
        self.record_button = tk.Button(self.controls_frame, text="Start Recording", command=self.toggle_recording)
        self.record_button.grid(row=0, column=0, padx=3)
        self.screenshot_button = tk.Button(self.controls_frame, text="Screenshot", command=self.take_screenshot)
        self.screenshot_button.grid(row=0, column=1, padx=3)
        self.zoom_button = tk.Button(self.controls_frame, text="Zoom In", command=self.toggle_zoom)
        self.zoom_button.grid(row=0, column=2, padx=3)
        self.switch_button = tk.Button(self.controls_frame, text="Switch Source", command=self.toggle_source)
        self.switch_button.grid(row=0, column=3, padx=3)
        # Bouton Interact (activé uniquement si la source est "screen")
        self.interact_button = tk.Button(self.controls_frame, text="Interact", command=self.toggle_interactive_mode, state=tk.DISABLED)
        self.interact_button.grid(row=0, column=4, padx=3)
        
        self.update_camera_list()
        self.update_frame()
        
        self.camera_listbox.bind("<<ListboxSelect>>", self.on_camera_select)
    
    # --- Récupération de la liste des caméras depuis le serveur ---
    def get_camera_list(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER_IP, LIST_PORT))
            data = s.recv(4)
            if not data:
                s.close()
                return []
            list_length = struct.unpack("!I", data)[0]
            data_bytes = b""
            while len(data_bytes) < list_length:
                packet = s.recv(4096)
                if not packet:
                    break
                data_bytes += packet
            s.close()
            if len(data_bytes) != list_length:
                return []
            # Format attendu : "nom;ip;source,nom2;ip2;source2,..."
            items = data_bytes.decode().split(',')
            cam_list = []
            for item in items:
                parts = item.split(';')
                if len(parts) == 3:
                    name, ip, source = parts
                    cam_list.append((name, ip, source))
            return cam_list
        except Exception as e:
            print("Erreur lors de la récupération de la liste des caméras :", e)
            return []
    
    def update_camera_list(self):
        self.cam_list = self.get_camera_list()
        self.camera_listbox.delete(0, tk.END)
        for name, ip, source in self.cam_list:
            display_name = self.camera_display_names.get(name, name)
            self.camera_listbox.insert(tk.END, f"{display_name} ({ip}) - {source}")
            # Si la caméra est déjà sélectionnée, mettre à jour sa source
            if self.selected_camera == name:
                self.selected_camera_source = source
                # Désactiver ou activer le bouton interact selon la source
                if source == "screen":
                    self.interact_button.config(state=tk.NORMAL)
                else:
                    self.interact_button.config(state=tk.DISABLED)
        self.master.after(2000, self.update_camera_list)
    
    def on_camera_select(self, event):
        selection = self.camera_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.cam_list):
                name, ip, source = self.cam_list[index]
                self.selected_camera = name
                self.selected_camera_ip = ip
                self.selected_camera_source = source
                self.zoom_offset_x = 0
                self.zoom_offset_y = 0
                # Activer le bouton interact si la source est "screen"
                if source == "screen":
                    self.interact_button.config(state=tk.NORMAL)
                else:
                    self.interact_button.config(state=tk.DISABLED)
                # Désactiver le mode interactif s'il était activé
                if self.interactive_mode:
                    self.toggle_interactive_mode()
    
    def rename_camera(self):
        if not self.selected_camera:
            messagebox.showwarning("Avertissement", "Aucune caméra sélectionnée.")
            return
        new_name = simpledialog.askstring("Renommer la caméra", "Entrez le nouveau nom:")
        if new_name:
            self.camera_display_names[self.selected_camera] = new_name
            print(f"Renommage de {self.selected_camera} en {new_name}")
            self.update_camera_list()
    
    def toggle_recording(self):
        if not self.recording:
            if self.current_frame is None:
                messagebox.showwarning("Avertissement", "Aucune image disponible pour démarrer l'enregistrement.")
                return
            self.recording = True
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            filename = time.strftime("recording_%Y%m%d_%H%M%S.avi")
            h, w, _ = self.current_frame.shape
            self.video_recorder = cv2.VideoWriter(filename, fourcc, 20.0, (w, h))
            self.record_button.config(text="Stop Recording")
            print("Enregistrement démarré :", filename)
        else:
            self.recording = False
            if self.video_recorder:
                self.video_recorder.release()
                self.video_recorder = None
            self.record_button.config(text="Start Recording")
            print("Enregistrement arrêté.")
    
    def take_screenshot(self):
        if self.current_frame is not None:
            filename = time.strftime("screenshot_%Y%m%d_%H%M%S.png")
            cv2.imwrite(filename, self.current_frame)
            print("Screenshot sauvegardé :", filename)
        else:
            messagebox.showwarning("Avertissement", "Aucune image à sauvegarder.")
    
    def toggle_zoom(self):
        self.zoom_active = not self.zoom_active
        if not self.zoom_active:
            self.zoom_offset_x = 0
            self.zoom_offset_y = 0
        self.zoom_button.config(text="Zoom Out" if self.zoom_active else "Zoom In")
    
    def toggle_source(self):
        if not self.selected_camera or not self.selected_camera_ip:
            messagebox.showwarning("Avertissement", "Aucune caméra sélectionnée.")
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.selected_camera_ip, COMMAND_PORT))
            s.sendall(b'toggle_source')
            s.close()
            print("Commande switch envoyée à", self.selected_camera_ip)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de switcher : {e}")
    
    # --- Fonctions pour le mode interactif ---
    def toggle_interactive_mode(self):
        self.interactive_mode = not self.interactive_mode
        if self.interactive_mode:
            self.interact_button.config(text="Stop Interact")
            # Bind des événements souris pour interaction
            self.video_label.bind("<Motion>", self.send_mouse_move)
            self.video_label.bind("<Button-1>", self.send_mouse_click)
            print("Mode interactif activé")
        else:
            self.interact_button.config(text="Interact")
            self.video_label.unbind("<Motion>")
            self.video_label.unbind("<Button-1>")
            print("Mode interactif désactivé")
    
    def send_mouse_move(self, event):
        x = event.x
        y = event.y
        self.send_mouse_event("move", x, y)
    
    def send_mouse_click(self, event):
        x = event.x
        y = event.y
        self.send_mouse_event("click", x, y)
    
    def send_mouse_event(self, event_type, x, y):
        if not self.selected_camera_ip:
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.selected_camera_ip, COMMAND_PORT))
            command = f"mouse_{event_type}:{x}:{y}".encode()
            s.sendall(command)
            s.close()
        except Exception as e:
            print(f"Erreur lors de l'envoi de l'événement souris: {e}")
    
    def start_drag(self, event):
        if self.zoom_active:
            self.is_dragging = True
            self.start_x = event.x
            self.start_y = event.y
    
    def during_drag(self, event):
        if self.zoom_active and self.is_dragging:
            dx = event.x - self.start_x
            dy = event.y - self.start_y
            self.zoom_offset_x += dx * 0.5
            self.zoom_offset_y += dy * 0.5
            self.start_x = event.x
            self.start_y = event.y
    
    def end_drag(self, event):
        self.is_dragging = False
    
    # --- Récupérer la frame depuis le serveur ---
    def get_frame_from_server(self, camera_name):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((SERVER_IP, VISU_PORT))
            s.sendall(camera_name.encode())
            data = s.recv(4)
            if not data:
                s.close()
                return None
            frame_length = struct.unpack("!I", data)[0]
            if frame_length == 0:
                s.close()
                return None
            frame_data = b""
            while len(frame_data) < frame_length:
                packet = s.recv(4096)
                if not packet:
                    break
                frame_data += packet
            s.close()
            if len(frame_data) == frame_length:
                nparr = np.frombuffer(frame_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                return frame
            else:
                return None
        except Exception as e:
            print("Erreur lors de la récupération de l'image :", e)
            return None
    
    def update_frame(self):
        if self.selected_camera:
            frame = self.get_frame_from_server(self.selected_camera)
            if frame is not None:
                self.current_frame = frame.copy()
                if self.zoom_active:
                    h, w, _ = frame.shape
                    center_x = w // 2 + int(self.zoom_offset_x)
                    center_y = h // 2 + int(self.zoom_offset_y)
                    rx = w // 4
                    ry = h // 4
                    center_x = max(rx, min(w - rx, center_x))
                    center_y = max(ry, min(h - ry, center_y))
                    frame = frame[center_y - ry:center_y + ry, center_x - rx:center_x + rx]
                    frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=pil_image)
                self.video_label.imgtk = imgtk
                self.video_label.config(image=imgtk)
                if self.recording and self.video_recorder:
                    self.video_recorder.write(self.current_frame)
        self.master.after(30, self.update_frame)

if __name__ == '__main__':
    root = tk.Tk()
    app = Visualiseur(root)
    root.mainloop()
