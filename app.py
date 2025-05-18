import os
import json
import base64
import sys
import time

import eel
import cv2
import numpy as np

import threading
import concurrent.futures

import random

# ThreadPool ve kilit
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
coord_lock = threading.Lock()


# -> Arka planda en son işlenmiş sonuçları tutacak
frame_lock = threading.Lock()
latest_data = None    # {"frame":..., "overlay":..., "parkingStatus":..., "colors":..., "fps":...}
processing_thread = None

sys.path.append("C:/Users/dogu_/OneDrive/Masaüstü/CombinedAppf/libs")
sys.path.insert(0 , "C:/Users/dogu_/OneDrive/Masaüstü/CombinedAppf")
from libs.camera import Camera

# Initialize eel with the web folder
current_dir = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(current_dir, "web")
eel.init(web_dir)

# Global variables
camera = None
coordinates = {}
workStatus = False
imageCoordDrawed = None
coordinate_Area = None
coordinate_parkCell = None
coordinate = None
frame = None
frameHeight = 0
frameWidth = 0
miliSecond = 1
samplingImageSize = 128
samplingImageDotControl = 3000
noktalar_son = np.float32([[0, 0], [0, 128], [128, 128], [128, 0]])
coordinateFileAdress = ""
selectedCameraDevice = 0
resize_value_global = 100
last_frame_time = None


def _processing_loop():
    """
    Arka planda kameradan kare alıp işleyerek
    en son sonucu global latest_data’ya yazar.
    """
    global latest_data, last_frame_time, workStatus, camera, resize_value_global, imageCoordDrawed, cell_colors

    while workStatus:
        now = time.time()
        # FPS hesaplama
        if last_frame_time is None:
            fps = 0.0
        else:
            fps = 1.0 / (now - last_frame_time)
        last_frame_time = now

        # 1) Kare al
        orig = camera.get_origin_frames()
        if orig is None:
            continue

        # 2) İşleme adımları (HSV → morfoloji → find_area …)
        imgHSV     = cv2.cvtColor(orig, cv2.COLOR_BGR2HSV)
        imgGray    = cv2.cvtColor(imgHSV, cv2.COLOR_BGR2GRAY)
        imgBlur    = cv2.GaussianBlur(imgGray, (5, 5), 0)
        contrasted = cv2.convertScaleAbs(imgBlur, 1.5, 2)
        _, imgThresh = cv2.threshold(contrasted, 160, 255, cv2.THRESH_BINARY)
        imgDilated = cv2.morphologyEx(imgThresh, cv2.MORPH_OPEN, (5, 5))

        # 3) Overlay güncelle
        find_area(imgDilated)

        # 4) Ölçekleme
        if resize_value_global != 100:
            disp_frame   = camera.resize_frame(orig, resize_value_global)
            disp_overlay = camera.resize_frame(imageCoordDrawed, resize_value_global)
        else:
            disp_frame   = orig
            disp_overlay = imageCoordDrawed

        # 5) Birleştir ve FPS yaz
        combined = cv2.add(disp_frame, disp_overlay)
        cv2.putText(
            combined,
            f"FPS: {fps:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )

        # 6) Encode kare
        processed = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
        _, buf1 = cv2.imencode(".jpg", processed)
        jpg_b64 = base64.b64encode(buf1).decode("utf-8")

        # 7) Encode statik overlay
        _, buf2 = cv2.imencode(".jpg", imageCoordDrawed)
        overlay_b64 = base64.b64encode(buf2).decode("utf-8")

        # 8) Status ve renkler
        status_data = get_parking_status()
        color_map   = { f"{a}{c}": rgb for (a,c), rgb in cell_colors.items() }

        # 9) Sonucu kaydet
        with frame_lock:
            latest_data = {
                "success":       True,
                "frame":         jpg_b64,
                "overlay":       overlay_b64,
                "parkingStatus": status_data,
                "colors":        color_map,
                "fps":           round(fps,1)
            }

        # CPU’yu rahatlatmak için kısa uyku
        time.sleep(0.01)

# Exposed functions to JavaScript
@eel.expose
def find_camera_devices():
    camera_selections = []
    try:
        index = 0
        while True:
            cap = cv2.VideoCapture(index)
            if not cap.read()[0]:
                break
            else:
                camera_selections.append(index)
            cap.release()
            index += 1
        return camera_selections
    except Exception:
        return []


@eel.expose
def start_video(camera_source, coordinate_file, resize_value):
    global camera, coordinates, workStatus, imageCoordDrawed, coordinateFileAdress, selectedCameraDevice, cell_colors
    global resize_value_global,processing_thread
    cell_colors = {}  # ('area','cell') -> (B,G,R)

    # Eğer bir önceki oturum hâlâ çalışıyorsa önce durdur
    if workStatus:
        # iş parçacığını kapat
        workStatus = False
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=1.0)
        # kamera objesini kapat
        try: camera.camera.release()
        except: pass

    workStatus = True
    resize_value_global = resize_value
    coordinateFileAdress = coordinate_file
    selectedCameraDevice = camera_source

    try:
        with open(coordinateFileAdress, "r") as coordinates_file:
            coordinates = json.load(coordinates_file)
            cell_colors.clear()
            for area, cells in coordinates.items():
                for cell in cells:
                    # her hücreye rastgele bir renk
                    cell_colors[(area, cell)] = (
                        random.randint(50,255),
                        random.randint(50,255),
                        random.randint(50,255)
                    )
    except Exception as exc:
        return {"error": f"Koordinat dosyası okunurken hata oluştu - {str(exc)}"}

    try:
        create_black_image()
        camera = Camera(cam_source=selectedCameraDevice)

        test_frame = camera.get_origin_frames()
        if test_frame is None:
            return {"error": f"Kaynak açıldı ama kare alınamadı: {camera_source}"}


        processing_thread = threading.Thread(
            target=_processing_loop,
            daemon=True
        )
        processing_thread.start()

        return {"success": True}
    except Exception as exc:
        return {
            "error": f"Görüntü kaynağı açılırken sorun ile karşılaşıldı - {str(exc)}"
        }
    


@eel.expose
def stop_video():
    global workStatus, camera, processing_thread
    workStatus = False
    

    # 2) İş parçacığının bitmesini bekle
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=1.0)

    # 3) Kamerayı kapat
    try:
        camera.camera.release()
    except:
        pass

    camera = None
    return {"success": True}


@eel.expose
def get_frame(state_name=""):
    """
    Artık CPU‐yoğun işleme arka planda _processing_loop() içinde yapılıyor.
    Bu fonksiyon en son işlenen veriyi anında döner.
    """

    global latest_data, camera, workStatus

    if not workStatus or camera is None:
        return {"success": False, "message": "Camera not started"}

    # Kilit altından en son işlenmiş çıktıyı al
    with frame_lock:
        data = latest_data.copy() if latest_data else None

    if not data:
        return {"success": False, "message": "Henüz frame işlenmedi"}

    # Eğer state_name eklemek isterseniz burada yapabilirsiniz:
    if state_name:
        # data["frame"] üzerinde metin yazdırmak isterseniz,
        # ya da ayrı bir overlay/jpg oluşturmak isterseniz,
        # aşağıda örnek vardır (isteğe bağlı):
        #
        # import cv2, base64
        # # 1) base64'ten decode
        # img_bytes = base64.b64decode(data["frame"])
        # np_arr    = np.frombuffer(img_bytes, np.uint8)
        # frame_rgb = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        # # 2) metni ekle
        # cv2.putText(frame_rgb, state_name, (10, frame_rgb.shape[0]-10),
        #             cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)
        # # 3) yeniden encode
        # _, buf = cv2.imencode(".jpg", frame_rgb)
        # data["frame"] = base64.b64encode(buf).decode("utf-8")
        pass

    return data



@eel.expose
def handle_coordinate_file(file_content, file_name):
    """Handle coordinate file uploaded from frontend"""
    try:
        temp_path = os.path.join(current_dir, "temp", file_name)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)

        with open(temp_path, "w") as f:
            f.write(file_content)

        return {"success": True, "path": temp_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@eel.expose
def handle_video_file(file_path):
    """Handle video file path from frontend"""
    # For video files, we might just need the path
    # This is a simplified version since browser can't provide full path
    return {"success": True, "path": file_path}


@eel.expose
def create_coordinate_file(file_name, file_content="{}"):
    """Create a new coordinate file with optional content"""
    try:
        if not file_name:
            return {"success": False, "message": "Dosya ismi boş olamaz"}

        # Make sure we have a .json extension
        if not file_name.endswith(".json"):
            file_name += ".json"

        save_path = os.path.join(current_dir, "coordinates", file_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, "w") as new_file:
            new_file.write(file_content)

        return {
            "success": True,
            "message": f"Dosyanız başarılı bir şekilde oluşturuldu: {file_name}",
            "path": save_path,
        }
    except Exception as exc:
        return {"success": False, "message": f"Dosyanız oluşturuldamadı: {str(exc)}"}


# TODO
@eel.expose
def select_folder():
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Konum Seçiniz")
    root.destroy()

    return folder_path if folder_path else ""


# Helper functions
def create_black_image():
    global imageCoordDrawed, frameHeight, frameWidth, cell_colors

    try:
        # 1) Capture a sample frame to get dimensions
        sample = cv2.VideoCapture(selectedCameraDevice)
        ret, image_sample = sample.read()
        sample.release()
        if not ret:
            raise RuntimeError(f"Unable to read from source {selectedCameraDevice}")

        frameHeight, frameWidth = image_sample.shape[:2]
        # 2) Create a blank image for the overlay
        imageCoordDrawed = np.zeros((frameHeight, frameWidth, 3), dtype=np.uint8)

        # 3) Draw each parking cell polygon with its assigned color
        for area, cells in coordinates.items():
            for cell, (pts, state) in cells.items():
                # Convert point list to numpy array of ints
                polygon = np.array(pts, dtype=np.int32)
                # Lookup the color for this (area, cell), fallback to green/red
                drawColor = cell_colors.get(
                    (area, cell),
                    (0, 150, 0) if state else (0, 0, 150)
                )
                # Fill the polygon
                cv2.fillPoly(imageCoordDrawed, [polygon], drawColor)
                # Put the label text at the first vertex
                x, y = polygon[0]
                cv2.putText(
                    imageCoordDrawed,
                    cell,
                    (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

        return True

    except Exception as exc:
        print(f"Error creating black image: {exc}")
        return False

def _evaluate_cell(args):
    """
    args = (area, cell, coord, dilated)
    Returns (area, cell, coord, new_state_bool, color_tuple)
    """
    area, cell, coord, dilated = args
    from math import isclose

    # Perspektif dönüşümü
    noktalar = np.float32(coord[0])
    degisim  = cv2.getPerspectiveTransform(noktalar, noktalar_son)
    warped   = cv2.warpPerspective(dilated, degisim, (0, 0))
    crop     = warped[0:samplingImageSize, 0:samplingImageSize]

    # Boşluk kontrolü
    count = cv2.countNonZero(crop)
    new_state = count < samplingImageDotControl
    # Renk seçimi
    color = (0,150,0) if new_state else (0,0,150)

    return area, cell, coord, new_state, color

def find_area(dilated):
    """
    Scans each parking cell in parallel, updates the overlay image
    and the in-memory coordinates dict, and persists changes to disk.
    """
    global coordinates, imageCoordDrawed, cell_colors

    # 1) Build a list of tasks: (area, cell, [pts, state], dilated_image)
    tasks = [
        (area, cell, coordinates[area][cell], dilated)
        for area in coordinates
        for cell in coordinates[area]
    ]

    # 2) Execute in thread pool
    results = executor.map(_evaluate_cell, tasks)

    updated = False
    # 3) Process results
    for area, cell, coord, new_state, color in results:
        pts, _ = coord  # coord == [pts_list, old_state]
        polygon = np.array(pts, dtype=np.int32)

        # Always redraw this cell with its color
        cv2.fillPoly(imageCoordDrawed, [polygon], color)
        # Label it
        x, y = polygon[0]
        cv2.putText(
            imageCoordDrawed,
            cell,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        # If the state changed, update in-memory and mark for saving
        if coordinates[area][cell][1] != new_state:
            with coord_lock:
                coordinates[area][cell][1] = new_state
            updated = True

    # 4) If any cell changed state, persist to JSON
    if updated:
        try:
            with open(coordinateFileAdress, "w+", encoding="utf-8") as f:
                json.dump(coordinates, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing coordinates JSON: {e}")


def check_parking_space(img_crop):
    global coordinates, coordinate_Area, coordinate_parkCell, coordinate, imageCoordDrawed

    try:
        count = cv2.countNonZero(img_crop)

        if count < samplingImageDotControl:
            cell_state = True
            state_color = (0, 150, 0)
        else:
            cell_state = False
            state_color = (0, 0, 150)

        if coordinate[1] != cell_state:
            cv2.fillPoly(imageCoordDrawed, [np.array(coordinate[0])], state_color)
            coordinates[coordinate_Area][coordinate_parkCell][1] = cell_state

        with open(coordinateFileAdress, "w+") as coordfile_write:
            json.dump(coordinates, coordfile_write, indent=2)

    except Exception as exc:
        print(f"Check parking space error: {exc}")


def get_parking_status():
    status_data = {}

    try:
        for area in coordinates:
            status_data[area] = {}
            for cell in coordinates[area]:
                status = "BOS" if coordinates[area][cell][1] else "DOLU"
                status_data[area][cell] = status
    except Exception as exc:
        print(f"Error getting parking status: {exc}")

    return status_data


@eel.expose
def handle_video_upload(raw_bytes):
    try:
        # Create a temporary directory for videos if it doesn't exist
        video_dir = os.path.join(current_dir, "temp_videos")
        os.makedirs(video_dir, exist_ok=True)

        # Generate a unique filename
        filename = f"video_{int(time.time())}.mp4"
        filepath = os.path.join(video_dir, filename)

        # Save the video file - don't try to convert with bytes() again
        with open(filepath, "wb") as f:
            # raw_bytes is already a bytes-like object from JavaScript
            f.write(raw_bytes)

        return {"success": True, "path": filepath}
    except Exception as e:
        return {"success": False, "error": str(e)}


@eel.expose
def start_selector(camera_source, coordinate_file, area_name, cell_name):
    """
    Birden fazla hücre seçimi: önceki çizimleri gösterir,
    4 nokta seç ve Enter ile kaydet, Esc ile tamamen bitir.
    Tıklama yaptıkça noktalar anında görünür.
    """
    import cv2, json
    import numpy as np
    from pathlib import Path

    # JSON’u yükle veya oluştur
    coords = {}
    if Path(coordinate_file).exists():
        with open(coordinate_file, "r", encoding="utf-8") as f:
            coords = json.load(f)
    if area_name not in coords or not isinstance(coords[area_name], dict):
        coords[area_name] = {}

    # Tek kare oku
    cap = cv2.VideoCapture(camera_source)
    if not cap.isOpened():
        return {"success": False, "error": f"Kaynak açılamadı: {camera_source}"}
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return {"success": False, "error": "Kare okunamadı"}

    pts = []
    added_cells = []
    win = "Konum Seçimi"
    instructions = "4 nokta seç, Enter=Kaydet, Esc=Bitir"

    def on_click(ev, x, y, flags, param):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y))

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)

    while True:
        disp = frame.copy()

        # ► Önceki hücreleri çiz
        for cell, data in coords[area_name].items():
            pts_arr = np.array(data[0], dtype=np.int32)
            cv2.polylines(disp, [pts_arr], isClosed=True, color=(0,200,0), thickness=2)
            x0, y0 = data[0][0]
            cv2.putText(disp, cell, (x0, y0),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,200,0), 2)

        # ► Şu an seçilen noktaları anında çiz
        for idx, (x, y) in enumerate(pts, start=1):
            cv2.circle(disp, (x, y), 5, (0,255,255), -1)
            cv2.putText(disp, str(idx), (x+8, y-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)

        # ► Talimat metnini ekle
        cv2.rectangle(disp, (0,0), (disp.shape[1], 30), (0,0,0), -1)
        cv2.putText(disp, instructions, (10,20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

        cv2.imshow(win, disp)
        key = cv2.waitKey(1) & 0xFF   # <-- Burayı 1 ms bekleyecek şekilde güncelledik

        if key == 13:  # Enter
            if len(pts) == 4:
                # Hücre ismini otomatik oluştur
                idx = len(coords[area_name]) + 1
                cell_name = f"{area_name}{idx}"


                coords[area_name][cell_name] = [
                    [[int(x), int(y)] for x, y in pts],
                    False
                ]
                added_cells.append(cell_name)

                # JSON dosyasına yaz
                with open(coordinate_file, "w+", encoding="utf-8") as f:
                    json.dump(coords, f, indent=2, ensure_ascii=False)

                # Yeni seçim için sıfırla
                pts = []
                instructions = f"'{cell_name}' kaydedildi! 4 nokta seç veya Esc"
            else:
                instructions = "Önce 4 nokta seçin!"
        elif key == 27:  # Esc
            break

    cv2.destroyWindow(win)
    return {"success": True, "cells": added_cells}



@eel.expose
def get_coordinates():
    # global coordinates zaten loaded
    return coordinates


@eel.expose
def select_video():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Video Dosyası Seç",
        filetypes=[("Video Dosyaları", "*.mp4 *.avi *.mov *.mpeg")]
    )
    root.destroy()
    return path or ""



class Application:
    def __init__(self):
        # Configure window options
        window_options = {
            "size": (1600, 900),
            "position": (0, 0),
            # 'title': "Park Area Finder (PAF)",
            # 'icon': '../assets/AppIcon.ico'
        }

        try:
            # Try to use Chrome in app mode
            eel.start(
                "index.html",
                mode="chrome-app",
                port=0,
                cmdline_args=["--start-fullscreen"],
                **window_options,
            )
        except EnvironmentError:
            # Fall back to default browser if Chrome isn't available
            try:
                eel.start("index.html", mode="chrome", port=0, **window_options)
            except Exception:
                eel.start("index.html", mode="default", port=0, **window_options)


if __name__ == "__main__":
    app = Application()
    
