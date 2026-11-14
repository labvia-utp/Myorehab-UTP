#!/usr/bin/env python3
"""
Modified version of 005_merge_data.py.

Main changes:
- Explicitly locates the device XML and the synchronization AUX channel.
- Detects edges of the digital signal rather than generic maxima across all channels.
- Uses the EMG frequency declared in the XML.
- Calculates the actual trigger frequency for each movement.
- Crops a window based on the measured duration of 3000 triggers, instead of a fixed 30 s.
- Reports missed/extra pulses and multiple pulse trains during execution.
- If multiple trains exist, automatically uses the last one as the final trial.
* Saves the output as MAT v7.3 (HDF5), suitable for large files.

Important: This version does NOT interpolate pulses, timestamps, kinematics, or EMG.
Potential missed pulses are only estimated and printed to the console; edges and
synchronization metrics are not saved in the MAT file.

Example execution from the dataset root:

    python utils/005_merge_data_v2.py --base S001/recording

The output is saved to:

    S001/recording/S001_mod.mat

To validate a trial without generating the MAT file:

    python utils/005_merge_data_v2.py \
        --base S001/recording --trial S001_111 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def robust_untar(archive: Path, dest: Path) -> None:
    try:
        try:
            with tarfile.open(archive, mode="r:*") as tf:
                tf.extractall(dest, filter="data")  # type: ignore[arg-type]
        except TypeError:
            with tarfile.open(archive, mode="r:*") as tf:
                tf.extractall(dest)
    except tarfile.ReadError:
        import shutil

        shutil.unpack_archive(str(archive), str(dest))


def find_device_xml(folder: Path) -> Path:
    """Encuentra el XML que contiene el nodo Device, ignorando el orden de archivos."""
    for xml_path in folder.rglob("*.xml"):
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            continue
        if local_name(root.tag) == "Device" or any(
            local_name(elem.tag) == "Device" for elem in root.iter()
        ):
            return xml_path
    raise FileNotFoundError("No se encontró el XML del dispositivo dentro del .otb+")


def parse_device_info(xml_path: Path) -> Tuple[int, float, int]:
    """
    Devuelve (número de canales, frecuencia EMG, índice AUX 0-based).

    Se prefiere la entrada directa de SyncStation cuyo canal no está marcado
    como MustBeDeleted.
    """
    root = ET.parse(xml_path).getroot()
    device = root if local_name(root.tag) == "Device" else None
    if device is None:
        device = next(
            (elem for elem in root.iter() if local_name(elem.tag) == "Device"),
            None,
        )
    if device is None:
        raise ValueError(f"No existe un nodo Device en {xml_path.name}")

    attrs = {key.lower(): value for key, value in device.attrib.items()}
    nch = int(attrs["devicetotalchannels"])
    fs_emg = float(attrs["samplefrequency"])

    candidates: List[Tuple[int, bool]] = []
    for adapter in device.iter():
        if local_name(adapter.tag) != "Adapter":
            continue
        adapter_id = adapter.attrib.get("ID", "")
        if adapter_id != "Direct connection to Syncstation Input":
            continue
        start = adapter.attrib.get("ChannelStartIndex")
        if start is None:
            continue
        marked_for_deletion = any(
            channel.attrib.get("Prefix", "") == "MustBeDeleted"
            for channel in adapter
            if local_name(channel.tag) == "Channel"
        )
        candidates.append((int(start), marked_for_deletion))

    if not candidates:
        raise ValueError(f"No se encontró la entrada AUX de SyncStation en {xml_path.name}")

    sync_idx = next(
        (index for index, marked in candidates if not marked),
        candidates[0][0],
    )
    if not 0 <= sync_idx < nch:
        raise ValueError(f"Índice AUX {sync_idx} fuera de rango para NCH={nch}")
    return nch, fs_emg, sync_idx


def read_sig_matrix(sig_path: Path, nch: int, dtype: str = "<i2") -> np.ndarray:
    raw = np.fromfile(sig_path, dtype=np.dtype(dtype))
    if raw.size % nch != 0:
        nearest = (raw.size // nch) * nch
        print(
            f"[WARN] {sig_path.name}: {raw.size} valores no divisibles por "
            f"NCH={nch}; se trunca a {nearest}."
        )
        raw = raw[:nearest]
    return raw.reshape((nch, -1), order="F")


def detect_sync_edges(
    signal: np.ndarray,
    fs_emg: float,
    min_distance_ms: float = 5.0,
) -> np.ndarray:
    """
    Detecta el comienzo de cada pulso mediante transiciones inactivo->activo.

    La polaridad se decide comparando la excursión positiva y negativa respecto
    a la mediana. El percentil 99.9/0.1 evita depender de mean*factor.
    """
    sig = np.asarray(signal, dtype=float)
    baseline = float(np.median(sig))
    high_level = float(np.percentile(sig, 99.9))
    low_level = float(np.percentile(sig, 0.1))

    positive_range = high_level - baseline
    negative_range = baseline - low_level
    if max(positive_range, negative_range) <= 0:
        raise RuntimeError("El canal AUX no presenta variación detectable")

    if positive_range >= negative_range:
        threshold = baseline + positive_range / 2.0
        active = sig > threshold
    else:
        threshold = baseline - negative_range / 2.0
        active = sig < threshold

    edges = np.flatnonzero(active & ~np.r_[False, active[:-1]])
    if edges.size == 0:
        raise RuntimeError("No se detectaron flancos en el canal AUX")

    min_distance = max(1, int(round(fs_emg * min_distance_ms / 1000.0)))
    accepted = [int(edges[0])]
    for edge in edges[1:]:
        if int(edge) - accepted[-1] >= min_distance:
            accepted.append(int(edge))
    return np.asarray(accepted, dtype=np.int64)


def analyze_sync_clock(
    edges: np.ndarray,
    fs_emg: float,
    new_train_gap_seconds: float = 1.0,
) -> Dict[str, Any]:
    """
    Estima el reloj real sin insertar pulsos.

    Los intervalos aproximadamente dobles/triples se contabilizan únicamente
    como posibles pulsos perdidos. Sólo una pausa larga (1 s por defecto)
    separa trials; si hay varios, se selecciona automáticamente el último.
    """
    if edges.size < 3:
        raise RuntimeError("No hay suficientes pulsos para estimar la frecuencia")

    intervals = np.diff(edges).astype(float)

    # Una pérdida breve del AUX no crea un nuevo trial. Sólo las pausas largas
    # separan intentos de grabación y, por criterio experimental, se usa el último.
    new_train_gap_samples = float(new_train_gap_seconds * fs_emg)
    split_points = np.flatnonzero(intervals >= new_train_gap_samples) + 1
    separation_gaps = intervals[split_points - 1]
    trains = [train for train in np.split(edges, split_points) if train.size > 0]
    selected_edges = trains[-1]
    if selected_edges.size < 3:
        raise RuntimeError("El último tren no tiene pulsos suficientes")

    selected_intervals = np.diff(selected_edges).astype(float)
    selected_median = float(np.median(selected_intervals))
    selected_regular = selected_intervals[
        (selected_intervals >= 0.5 * selected_median)
        & (selected_intervals <= 1.5 * selected_median)
    ]
    if selected_regular.size == 0:
        raise RuntimeError("No se pudo estimar el periodo del último tren")

    # La media conserva la fracción 20/21 muestras producida por la
    # cuantización a 2000 Hz; la mediana sola daría 21.
    period_samples = float(np.mean(selected_regular))
    effective_fs = float(fs_emg / period_samples)

    possible_missing = 0
    for interval in selected_intervals:
        ratio = interval / period_samples
        if ratio > 1.5:
            possible_missing += max(0, int(round(ratio)) - 1)

    return {
        "selected_edges": selected_edges,
        "separation_gaps_samples": separation_gaps.astype(float),
        "period_samples": period_samples,
        "effective_fs": effective_fs,
        "possible_missing": int(possible_missing),
        "train_count": int(len(trains)),
    }


def drop_kinematics_columns_like_matlab(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    k = 1
    for _ in range(21):
        for _ in range(3):
            index = (k + 3) - 1
            if 0 <= index < len(cols):
                cols.pop(index)
        k += 3
        if not cols:
            break
    to_drop = set(range(63, 76))
    return df[[column for index, column in enumerate(cols) if index not in to_drop]].copy()


def ensure_kinematic_columns(df: pd.DataFrame, target_columns: int = 63) -> pd.DataFrame:
    if df.shape[1] > target_columns:
        print(f"[INFO] kin.columns: {df.shape[1]} -> {target_columns}")
        return df.iloc[:, :target_columns].copy()
    if df.shape[1] < target_columns:
        print(f"[WARN] kin.columns: {df.shape[1]} -> {target_columns} con NaN")
        df = df.copy()
        for index in range(df.shape[1], target_columns):
            df[f"Extra_{index + 1}"] = np.nan
    return df.iloc[:, :target_columns].copy()


def build_emg_labels() -> List[str]:
    return [
        f"Matrix {matrix} - Channel {channel}"
        for matrix in range(1, 5)
        for channel in range(1, 33)
    ]


def build_fixed_emg_channel_map() -> List[int]:
    indices: List[int] = []
    for first, last in [(1, 32), (39, 70), (77, 108), (115, 146)]:
        indices.extend(range(first - 1, last))
    return indices


def to_matlab_row_cell(labels: List[str]) -> np.ndarray:
    return np.array([labels], dtype=object)


def movement_name(file_stem: str, fallback_index: int) -> str:
    suffix = file_stem.rsplit("_", 1)[-1]
    if suffix.isdigit() and len(suffix) == 3:
        return f"M{suffix}"
    return f"Mx{fallback_index:03d}"


def pair_input_files(base: Path, trial: str | None = None) -> List[Tuple[Path, Path]]:
    emg_files = sorted((base / "emg").glob("*.otb+"))
    kin_files = sorted((base / "pose-3d").glob("*.csv"))
    emg_by_stem = {path.name.removesuffix(".otb+"): path for path in emg_files}
    kin_by_stem = {path.stem: path for path in kin_files}

    missing_kin = sorted(set(emg_by_stem) - set(kin_by_stem))
    missing_emg = sorted(set(kin_by_stem) - set(emg_by_stem))
    if missing_kin or missing_emg:
        details = []
        if missing_kin:
            details.append(f"sin cinemática: {missing_kin}")
        if missing_emg:
            details.append(f"sin EMG: {missing_emg}")
        raise RuntimeError("No se pudieron emparejar archivos por nombre; " + "; ".join(details))

    stems = sorted(emg_by_stem)
    if trial is not None:
        normalized_trial = trial.removesuffix(".otb+").removesuffix(".csv")
        stems = [stem for stem in stems if stem == normalized_trial]
        if not stems:
            raise RuntimeError(f"No se encontró el ensayo {normalized_trial}")
    return [(emg_by_stem[stem], kin_by_stem[stem]) for stem in stems]


def infer_subject_id(base: Path) -> str:
    for candidate in [base.name, base.parent.name]:
        if len(candidate) == 4 and candidate.startswith("S") and candidate[1:].isdigit():
            return candidate
    return "S000"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge EMG-cinemática con sincronización AUX sin interpolación."
    )
    parser.add_argument("--base", default=".", help="Carpeta con emg/ y pose-3d/")
    parser.add_argument(
        "--sync-channel",
        type=int,
        default=None,
        help="Canal AUX 1-based. Si se omite, se obtiene del XML.",
    )
    parser.add_argument("--expected-frames", type=int, default=3000)
    parser.add_argument("--nominal-kin-fs", type=float, default=100.0)
    parser.add_argument("--min-pulse-distance-ms", type=float, default=5.0)
    parser.add_argument(
        "--new-train-gap-seconds",
        type=float,
        default=1.0,
        help=(
            "Pausa mínima para considerar un nuevo trial. Huecos menores se "
            "registran como posibles pulsos perdidos (por defecto: 1 s)."
        ),
    )
    parser.add_argument(
        "--trial",
        default=None,
        help="Procesa sólo un ensayo, por ejemplo S017_111 (opcional).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Nombre/ruta del MAT de salida. Por defecto: S###_mod.mat",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite reemplazar el archivo de salida si ya existe.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y muestra métricas sin guardar un archivo MAT.",
    )
    args = parser.parse_args()

    base = Path(args.base).resolve()
    pairs = pair_input_files(base, trial=args.trial)
    if not pairs:
        print("ERROR: no se encontraron pares EMG/cinemática", file=sys.stderr)
        sys.exit(1)

    subject_id = infer_subject_id(base)
    output_path = (
        Path(args.output).resolve()
        if args.output
        else base / f"{subject_id}_mod.mat"
    )
    if not output_path.parent.exists():
        raise FileNotFoundError(f"No existe la carpeta de salida: {output_path.parent}")
    if output_path.exists() and not args.dry_run and not args.overwrite:
        raise FileExistsError(
            f"El archivo de salida ya existe: {output_path}. "
            "Usa --overwrite para reemplazarlo."
        )

    dataset: Dict[str, Any] = {
        # Se conserva la metadata del script original. Debe ajustarse si esta
        # copia se utiliza para otro participante.
        "participantInfo": {
            "Age": "36y",
            "Dexterity": "21.5s",
            "ForearmPerimeter": "6.25cm",
            "Gender": "Male",
            "Height": "178cm",
            "Injuries": "None",
            "Laterality": "Right",
        },
        "fileInfo": {
            "mat_format": "7.3",
            "storage": "HDF5",
            "interpolation_applied": False,
        },
        "kin": {
            # Se conserva la frecuencia nominal utilizada por la cinemática.
            "fs": float(args.nominal_kin_fs),
            "raw": {},
            "labels": None,
        },
        "emg": {
            "fs": None,
            "raw": {},
            "labels": to_matlab_row_cell(build_emg_labels()),
        },
    }

    fixed_emg_indices = build_fixed_emg_channel_map()
    common_emg_fs: float | None = None

    for number, (emg_path, kin_path) in enumerate(pairs, start=1):
        movement = movement_name(kin_path.stem, number)
        print(f"[{number}/{len(pairs)}] {movement}: {emg_path.name}")

        kin_df = ensure_kinematic_columns(
            drop_kinematics_columns_like_matlab(pd.read_csv(kin_path))
        )
        if len(kin_df) != args.expected_frames:
            print(
                f"[WARN] {movement}: cinemática con {len(kin_df)} filas; "
                f"se conserva sin truncar ni rellenar."
            )
        dataset["kin"]["raw"][movement] = kin_df.to_numpy(dtype=float)
        dataset["kin"]["labels"] = to_matlab_row_cell(list(kin_df.columns))

        with tempfile.TemporaryDirectory(dir=base) as temporary:
            extracted = Path(temporary)
            robust_untar(emg_path, extracted)
            sig_files = list(extracted.rglob("*.sig"))
            if len(sig_files) != 1:
                raise RuntimeError(
                    f"{emg_path.name}: se esperaba un .sig y se encontraron {len(sig_files)}"
                )
            device_xml = find_device_xml(extracted)
            nch, fs_emg, xml_sync_idx = parse_device_info(device_xml)
            emg_full = read_sig_matrix(sig_files[0], nch)

        if common_emg_fs is None:
            common_emg_fs = fs_emg
            dataset["emg"]["fs"] = fs_emg
        elif not np.isclose(common_emg_fs, fs_emg):
            raise RuntimeError(
                f"Frecuencia EMG inconsistente: {common_emg_fs} frente a {fs_emg}"
            )

        sync_idx = args.sync_channel - 1 if args.sync_channel else xml_sync_idx
        if not 0 <= sync_idx < nch:
            raise IndexError(f"Canal AUX {sync_idx + 1} fuera de rango para NCH={nch}")

        all_edges = detect_sync_edges(
            emg_full[sync_idx],
            fs_emg,
            min_distance_ms=args.min_pulse_distance_ms,
        )
        clock = analyze_sync_clock(
            all_edges,
            fs_emg,
            new_train_gap_seconds=args.new_train_gap_seconds,
        )
        selected_edges = np.asarray(clock["selected_edges"], dtype=np.int64)
        separation_gaps = np.asarray(
            clock["separation_gaps_samples"], dtype=float
        )

        # El periodo medido define la duración física de los 3000 frames. No
        # se remuestrean ni la cinemática ni el EMG.
        period_samples = float(clock["period_samples"])
        start_sample = int(selected_edges[0])
        requested_samples = int(round(args.expected_frames * period_samples))
        requested_end = start_sample + requested_samples
        end_sample = min(requested_end, emg_full.shape[1])
        clipped = end_sample < requested_end

        emg_out = np.full((end_sample - start_sample, 128), np.nan, dtype=float)
        for output_channel, source_channel in enumerate(fixed_emg_indices):
            if source_channel < nch:
                emg_out[:, output_channel] = emg_full[
                    source_channel, start_sample:end_sample
                ]

        detected_extra = max(0, int(selected_edges.size) - args.expected_frames)
        train_count = int(clock["train_count"])
        possible_missing = int(clock["possible_missing"])
        if selected_edges.size < args.expected_frames:
            qc_status = "REVIEW_LAST_TRAIN_INSUFFICIENT_PULSES"
        elif clipped:
            qc_status = "REVIEW_EMG_WINDOW_CLIPPED"
        elif train_count > 1 and possible_missing > 0:
            qc_status = "LAST_TRAIN_SELECTED_POSSIBLE_MISSING_PULSES"
        elif train_count > 1:
            qc_status = "LAST_TRAIN_SELECTED"
        elif possible_missing > 0:
            qc_status = "POSSIBLE_MISSING_PULSES_NOT_INTERPOLATED"
        else:
            qc_status = "OK"

        dataset["emg"]["raw"][movement] = emg_out
        # La frecuencia efectiva se calcula y se muestra en consola, pero por
        # ahora no se incorpora al MAT ni se asocia a cada trial cinemático.
        # Para guardarla en el futuro:
        # dataset["kin"].setdefault("fs_effective", {})[movement] = float(
        #     clock["effective_fs"]
        # )

        print(
            f"    AUX={sync_idx + 1}, pulsos_totales={all_edges.size}, "
            f"trenes={train_count}, ultimo_tren={selected_edges.size}, "
            f"extras_detectados={detected_extra}, "
            f"pausas_ms={np.round(separation_gaps / fs_emg * 1000, 3).tolist()}, "
            f"fs_real={clock['effective_fs']:.4f} Hz, "
            f"posibles_perdidos={possible_missing}, QC={qc_status}"
        )

    if args.dry_run:
        print("Dry run completado: no se guardó ningún archivo MAT.")
    else:
        try:
            import hdf5storage
        except ImportError as error:
            raise RuntimeError(
                "Para guardar MAT v7.3 instala hdf5storage en el entorno: "
                "pip install hdf5storage"
            ) from error

        temporary_output = output_path.with_name(
            f".{output_path.stem}.{uuid.uuid4().hex}.partial.mat"
        )
        print(f"Guardando MAT v7.3 en {output_path}...")
        try:
            hdf5storage.savemat(
                str(temporary_output),
                {subject_id: dataset},
                format="7.3",
                matlab_compatible=True,
                store_python_metadata=False,
                compress=True,
            )
            with temporary_output.open("rb") as saved_file:
                saved_header = saved_file.read(520)
            hdf5_signature = b"\x89HDF\r\n\x1a\n"
            is_hdf5 = saved_header.startswith(hdf5_signature) or (
                len(saved_header) >= 520 and saved_header[512:520] == hdf5_signature
            )
            if not is_hdf5:
                raise RuntimeError("El archivo generado no tiene una cabecera HDF5 válida")
            os.replace(temporary_output, output_path)
        except Exception:
            temporary_output.unlink(missing_ok=True)
            raise
        print("Done! Formato MAT v7.3/HDF5 verificado.")


if __name__ == "__main__":
    main()

