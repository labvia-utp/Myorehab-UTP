import os
import shutil
import argparse

# Configuración fija
EXTS = (".mp4", ".avi", ".mov", ".mkv")
CALIB_TOKEN = "_calib-"
CAM_DIRS = [f"cam{i}" for i in range(1, 6)]

def procesar_archivos(project_root: str, mode: str = "copy"):
    raw_data = os.path.join(project_root, "raw-data")
    dest_videos = os.path.join(project_root, "recording", "videos-raw")
    dest_calib  = os.path.join(project_root, "recording", "calibration")
    dest_emg    = os.path.join(project_root, "recording", "emg")

    if not os.path.isdir(raw_data):
        print(f"[ERROR] No existe la carpeta: {raw_data}")
        return

    os.makedirs(dest_videos, exist_ok=True)
    os.makedirs(dest_calib, exist_ok=True)
    os.makedirs(dest_emg, exist_ok=True)

    jobs = []

    # --- Videos (cam1..cam5) ---
    for cam in CAM_DIRS:
        camdir = os.path.join(raw_data, cam)
        if not os.path.isdir(camdir):
            continue
        for fname in os.listdir(camdir):
            if fname.lower().endswith(EXTS):
                src = os.path.join(camdir, fname)
                dst_base = dest_calib if CALIB_TOKEN in fname.lower() else dest_videos
                dst = os.path.join(dst_base, fname)
                jobs.append((src, dst, "video"))

    # --- Archivos EMG ---
    emgdir = os.path.join(raw_data, "emg")
    if os.path.isdir(emgdir):
        for fname in os.listdir(emgdir):
            src = os.path.join(emgdir, fname)
            if os.path.isfile(src):
                dst = os.path.join(dest_emg, fname)
                jobs.append((src, dst, "emg"))

    if not jobs:
        print("[INFO] No se encontraron archivos para procesar.")
        return

    copied = moved = skipped = errors = 0

    print(f"Proyecto: {project_root}")
    print(f"Archivos a procesar: {len(jobs)}")
    print(f"Modo: {'Copiar' if mode=='copy' else 'Mover'}")
    print("--------------------------------------------------")

    for src, dst, kind in jobs:
        try:
            if os.path.exists(dst):
                print(f"[SALTADO] Ya existe: {dst}")
                skipped += 1
                continue

            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if mode == "copy":
                shutil.copy2(src, dst)
                print(f"[COPIADO] {src} -> {dst}")
                copied += 1
            else:
                shutil.move(src, dst)
                print(f"[MOVIDO]  {src} -> {dst}")
                moved += 1
        except Exception as e:
            print(f"[ERROR]   {src} -> {dst} :: {e}")
            errors += 1

    print("--------------------------------------------------")
    print(f"Total: {len(jobs)} | Copiados: {copied} | Movidos: {moved} | "
          f"Saltados: {skipped} | Errores: {errors}")

def main():
    parser = argparse.ArgumentParser(description="Copiar o mover videos y EMG de raw-data → recording")
    parser.add_argument("project_root", help="Ruta al directorio del proyecto (ej: D:/nombre_carpeta/)")
    parser.add_argument("--mode", choices=["copy", "move"], default="copy",
                        help="Modo de operación: 'copy' (por defecto) o 'move'")
    args = parser.parse_args()

    procesar_archivos(args.project_root, args.mode)

if __name__ == "__main__":
    main()

# python 004_move_files.py D:/DATASET-MYOREHAB/S00# --mode copy

