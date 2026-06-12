import shutil  # Para copiar archivos
import os
import toml
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def create_structure(base_path, project_name, file_to_copy=None):
    """
    Crea la estructura:
    <base>/<project_name>/
        ├─ recording/
        │   ├─ calibration/
        │   └─ videos-raw/
        └─ raw-data/
            ├─ cam1/
            ├─ cam2/
            ├─ cam3/
            ├─ cam4/
            ├─ cam5/
            └─ emg/

    Copia (opcional) un archivo (p. ej. mediapipe_analyze.py) directamente en recording/.
    """
    project_root = os.path.join(base_path, project_name)
    recording_root = os.path.join(project_root, 'recording')
    raw_data_root = os.path.join(project_root, 'raw-data')

    # --- Crear estructura recording ---
    calibration_path = os.path.join(recording_root, 'calibration')
    videos_raw_path = os.path.join(recording_root, 'videos-raw')
    os.makedirs(calibration_path, exist_ok=True)
    os.makedirs(videos_raw_path, exist_ok=True)

    # --- Crear estructura raw-data ---
    os.makedirs(raw_data_root, exist_ok=True)
    for cam in ['cam1', 'cam2', 'cam3', 'cam4', 'cam5', 'emg']:
        os.makedirs(os.path.join(raw_data_root, cam), exist_ok=True)

    # Copiar archivo (opcional) directamente a recording/
    if file_to_copy:
        dest_path = os.path.join(recording_root, os.path.basename(file_to_copy))
        shutil.copy2(file_to_copy, dest_path)

    print(f"Estructura del proyecto creada en: {project_root}")
    return project_root

def create_config(base_path, project_name):
    model_folder = os.path.join(base_path, project_name, "recording")
    DEFAULT_CONFIG = {
        'project': project_name,
        'model_folder': model_folder,
        'nesting': 1,  # ajústalo si tu pipeline recorre por niveles
        'video_extension': 'mp4',
        'calibration': {
            'board_type': 'charuco',
            'board_size': [10, 7],
            'board_marker_bits': 4,
            'board_marker_dict_number': 50,
            'board_marker_length': 20,
            'board_square_side_length': 27,
            'animal_calibration': False,
            'fisheye': False,
        },
        'labeling': {
            'scheme': [
                ["WRIST", "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP"],
                ["WRIST", "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP"],
                ["WRIST", "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP"],
                ["WRIST", "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP"],
                ["WRIST", "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP"]
            ]
        },
        # Nota: mantengo tus claves con guion_bajo tal como las usaste aquí.
        # Si alguna herramienta (p.ej., Anipose) exige 'videos-raw' y 'pose-3d', podemos duplicarlas.
        'pipeline': {
            'videos_raw': 'videos-raw',       # relativo a model_folder (recording/)
            'pose_3d': 'pose-3d',
            'calibrations_results': 'calibration',
        },
        'triangulation': {
            'triangulate': 'true',
            'cam_regex': '-(cam[A-Z])',
            'cam_align': 'camA',
            'ransac': 'false',
            'optim': 'true',
            'constraints': [
                ["WRIST", "THUMB_CMC"], ["THUMB_CMC", "THUMB_MCP"], ["THUMB_MCP", "THUMB_IP"], ["THUMB_IP", "THUMB_TIP"],
                ["WRIST", "INDEX_FINGER_MCP"], ["INDEX_FINGER_MCP", "INDEX_FINGER_PIP"], ["INDEX_FINGER_PIP", "INDEX_FINGER_DIP"], ["INDEX_FINGER_DIP", "INDEX_FINGER_TIP"],
                ["WRIST", "MIDDLE_FINGER_MCP"], ["MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP"], ["MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP"], ["MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP"],
                ["WRIST", "RING_FINGER_MCP"], ["RING_FINGER_MCP", "RING_FINGER_PIP"], ["RING_FINGER_PIP", "RING_FINGER_DIP"], ["RING_FINGER_DIP", "RING_FINGER_TIP"],
                ["WRIST", "PINKY_MCP"], ["PINKY_MCP", "PINKY_PIP"], ["PINKY_PIP", "PINKY_DIP"], ["PINKY_DIP", "PINKY_TIP"]
            ],
            'scale_smooth': 25,
            'scale_length': 10,
            'scale_length_weak': 2,
            'reproj_error_threshold': 3,
            'score_threshold': 0.6,
            'n_deriv_smooth': 2,
        }
    }

    configfile = os.path.join(base_path, project_name, 'config.toml')
    with open(configfile, 'w') as f:
        toml.dump(DEFAULT_CONFIG, f)

class FolderInputApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Entrada de Información del Proyecto")

        # Nombre del proyecto
        ttk.Label(root, text="Nombre del Proyecto:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.project_name_var = tk.StringVar()
        ttk.Entry(root, textvariable=self.project_name_var, width=40).grid(row=0, column=1, padx=5, pady=5)

        # Ruta de carpeta (base)
        ttk.Label(root, text="Ruta de Carpeta (base):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.folder_path_var = tk.StringVar()
        ttk.Entry(root, textvariable=self.folder_path_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Button(root, text="Buscar...", command=self.browse_folder).grid(row=1, column=2, padx=5, pady=5)

        # Archivo para copiar en recording (opcional)
        ttk.Label(root, text="Archivo mediapipe_analyze.py (opcional):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.file_path_var = tk.StringVar()
        ttk.Entry(root, textvariable=self.file_path_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky="w")
        ttk.Button(root, text="Buscar archivo...", command=self.browse_file).grid(row=2, column=2, padx=5, pady=5)

        # Botón para enviar
        ttk.Button(root, text="Crear estructura", command=self.submit).grid(row=3, column=1, pady=15)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path_var.set(folder_selected)

    def browse_file(self):
        file_selected = filedialog.askopenfilename()
        if file_selected:
            self.file_path_var.set(file_selected)

    def submit(self):
        project_name = self.project_name_var.get().strip()
        base_path = self.folder_path_var.get().strip()
        file_to_copy = self.file_path_var.get().strip()

        # Validar entradas
        if not project_name:
            messagebox.showerror("Error de Entrada", "Introduce un nombre para el proyecto.")
            return

        if not base_path or not os.path.isdir(base_path):
            messagebox.showerror("Error de Entrada", "Selecciona una carpeta base válida.")
            return

        if file_to_copy and not os.path.isfile(file_to_copy):
            messagebox.showerror("Error de Entrada", "El archivo para copiar no es válido.")
            return

        try:
            project_root = create_structure(base_path, project_name, file_to_copy if file_to_copy else None)
            create_config(base_path, project_name)
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error: {e}")
            return

        messagebox.showinfo(
            "Éxito",
            f"Estructura creada en:\n{project_root}\n\n"
            f"Se generó config.toml y (si seleccionaste) se copió el archivo en 'recording/'.\n\n"
            f"Estructura creada:\n"
            f" - recording/calibration/\n"
            f" - recording/videos-raw/\n"
            f" - raw-data/cam1..cam5, emg"
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = FolderInputApp(root)
    root.mainloop()
