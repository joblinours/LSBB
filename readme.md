# Camera Server App

## Description

Ce projet est une application de serveur de caméra qui permet de visualiser, enregistrer et interagir avec des flux vidéo provenant de plusieurs caméras. L'application est composée de trois scripts principaux :

- `looker.py` : Interface utilisateur pour visualiser et interagir avec les flux vidéo.
- `cam.py` : Script client pour envoyer des flux vidéo et audio au serveur.
- `srv.py` : Serveur central pour gérer les connexions vidéo et audio des caméras.

## Prérequis

- Python 3.x
- Bibliothèques Python : `tkinter`, `socket`, `struct`, `cv2` (OpenCV), `numpy`, `PIL` (Pillow), `sounddevice`, `cryptography`, `mss`

## Installation

1. Clonez le dépôt :
    ```bash
    git clone https://github.com/joblinours/LSBB.git
    cd LSBB
    ```

2. Installez les dépendances :
    ```bash
    pip install opencv-python-headless numpy pillow sounddevice cryptography mss
    ```

## Utilisation

### Lancement du serveur

1. Exécutez le script `srv.py` pour démarrer le serveur central :
    ```bash
    python3 srv.py
    ```

### Lancement des clients caméra

1. Exécutez le script `cam.py` sur chaque machine client pour envoyer les flux vidéo et audio au serveur :
    ```bash
    python3 cam.py
    ```

### Interface de visualisation

1. Exécutez le script `looker.py` pour lancer l'interface utilisateur de visualisation :
    ```bash
    python3 looker.py
    ```

## Fonctionnalités

### `looker.py`

- Affichage des flux vidéo en temps réel.
- Enregistrement des vidéos.
- Capture d'écran.
- Zoom sur les flux vidéo.
- Interaction avec les flux vidéo (mode interactif).
- Renommage des caméras.

### `cam.py`

- Envoi des flux vidéo (webcam ou capture d'écran) au serveur.
- Envoi des flux audio au serveur.
- Basculer entre la webcam et la capture d'écran.

### `srv.py`

- Gestion des connexions vidéo et audio des caméras.
- Lecture audio en temps réel# Camera Server App
