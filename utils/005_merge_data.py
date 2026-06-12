#!/usr/bin/env python3
"""
Build S001.mat from pose-3d/*.csv and emg/*.otb+ with robust sync detection.
- Auto-detects sync channel if requested (scans all channels for digital-like pulses).
- Accepts --sync-channel (1-based) to force a specific channel.
- Always returns fixed shapes:
  * EMG: samples = duration_sec * 2000, channels = 128 (pads with NaN if needed)
  * KIN: samples = duration_sec * 100,  columns  = 63  (pads with NaN if needed)
- Forces labels dims: kin=1x63, emg=1x128 (MATLAB cell row vectors).

You can use the --pad-with-zero flag to use 0 instead of NaN in the padding;
the default is NaN so that it does not contaminate averages or metrics.

"""

from __future__ import annotations

import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
from scipy.io import savemat
from scipy.signal import find_peaks
import xml.etree.ElementTree as ET
import argparse


def local_name(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag


def parse_device_attrs(xml_path: Path) -> Tuple[int, float]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    device = None
    for elem in root.iter():
        if local_name(elem.tag) == "Device":
            device = elem
            break
    if device is None:
        raise ValueError(f"No <Device> node in {xml_path.name}")
    attrs = {k.lower(): v for k, v in device.attrib.items()}
    nch = int(attrs.get("devicetotalchannels"))
    fs = float(attrs.get("samplefrequency"))
    return nch, fs


def read_sig_matrix(sig_path: Path, nch: int, dtype="<i2") -> np.ndarray:
    raw = np.fromfile(sig_path, dtype=np.dtype(dtype))
    if raw.size % nch != 0:
        nearest = (raw.size // nch) * nch
        print(f"[WARN] {sig_path.name}: {raw.size} samples not divisible by NCH={nch}. Truncating to {nearest}.")
        raw = raw[:nearest]
    return raw.reshape((nch, -1), order="F")


def robust_untar(archive: Path, dest: Path) -> None:
    try:
        try:
            tar = tarfile.open(archive, mode="r:*")
            tar.extractall(dest, filter="data")  # type: ignore[arg-type]
            tar.close()
        except TypeError:
            with tarfile.open(archive, mode="r:*") as tf:
                tf.extractall(dest)
    except tarfile.ReadError:
        import shutil
        shutil.unpack_archive(str(archive), str(dest))


def drop_kinematics_columns_like_matlab(df: pd.DataFrame) -> pd.DataFrame:
    # Misma poda; después forzamos a 63 cols (trunc/pad) al construir labels y al guardar.
    cols = list(df.columns)
    k = 1  # MATLAB 1-based
    for _ in range(21):
        for _rm in range(3):
            idx = (k + 3) - 1  # 0-based
            if 0 <= idx < len(cols):
                cols.pop(idx)
        k += 3
        if not cols:
            break
    # Quitar 64..76 (1-based) -> 63..75
    to_drop_idx = set(range(63, 76))
    cols_final = [c for i, c in enumerate(cols) if i not in to_drop_idx]
    return df[cols_final].copy()


def build_emg_labels() -> List[str]:
    labels = []
    for a in range(1, 5):
        for b in range(1, 33):
            labels.append(f"Matrix {a} - Channel {b}")
    return labels  # 128


def detect_sync_channel(emg_mat: np.ndarray, factor: float = 5.0, min_peaks: int = 3) -> int:
    best_idx = 0
    best_count = -1
    best_height_sum = -1.0
    for ch in range(emg_mat.shape[0]):
        sig = emg_mat[ch, :]
        thr = float(np.mean(sig)) * factor
        peaks, props = find_peaks(sig, height=thr)
        count = peaks.size
        height_sum = float(np.sum(props["peak_heights"])) if count > 0 else 0.0
        if count > best_count or (count == best_count and height_sum > best_height_sum):
            best_idx = ch
            best_count = count
            best_height_sum = height_sum
    if best_count < min_peaks:
        stds = np.std(emg_mat, axis=1)
        best_idx = int(np.argmax(stds))
    return best_idx


def to_matlab_row_cell(labels: List[str], target_len: int, kind: str) -> np.ndarray:
    """
    Convierte lista de strings en cell row 1xN (savemat).
    Trunca o rellena con 'Extra_i' para alcanzar target_len.
    """
    if len(labels) > target_len:
        print(f"[INFO] {kind}: truncating {len(labels)} -> {target_len}")
        labels = labels[:target_len]
    elif len(labels) < target_len:
        print(f"[INFO] {kind}: padding {len(labels)} -> {target_len}")
        for i in range(len(labels), target_len):
            labels.append(f"Extra_{i+1}")
    return np.array([labels], dtype=object)


def build_fixed_emg_channel_map() -> List[int]:
    """
    Devuelve SIEMPRE 128 índices 0-based deseados, siguiendo los bloques
    1-32, 39-70, 77-108, 115-146 (1-based). No se recortan a NCH aquí.
    Los que excedan NCH se rellenarán con NaN en la matriz final.
    """
    ranges = [(1, 32), (39, 70), (77, 108), (115, 146)]
    idx = []
    for a, b in ranges:
        idx.extend(list(range(a - 1, b)))  # 0-based
    assert len(idx) == 128
    return idx


def pad_or_trunc_rows(M: np.ndarray, target_rows: int) -> np.ndarray:
    """
    Asegura que M tenga target_rows filas. Si faltan, rellena con NaN; si sobran, trunca.
    """
    r, c = M.shape
    if r == target_rows:
        return M
    if r > target_rows:
        return M[:target_rows, :]
    # pad
    out = np.full((target_rows, c), np.nan, dtype=float)
    out[:r, :] = M
    return out


def pad_or_trunc_cols(M: np.ndarray, target_cols: int) -> np.ndarray:
    """
    Asegura que M tenga target_cols columnas. Si faltan, rellena con NaN; si sobran, trunca.
    """
    r, c = M.shape
    if c == target_cols:
        return M
    if c > target_cols:
        return M[:, :target_cols]
    out = np.full((r, target_cols), np.nan, dtype=float)
    out[:, :c] = M
    return out


def main():
    ap = argparse.ArgumentParser(description="Merge EMG (.otb+) and kinematics (.csv) into S001.mat with robust sync.")
    ap.add_argument("--base", type=str, default=".", help="Carpeta base con emg/ y pose-3d/")
    ap.add_argument("--sync-channel", type=int, default=None, help="Canal de sincronía 1-based (anula autodetección)")
    ap.add_argument("--peak-factor", type=float, default=5.0, help="Umbral de picos = mean*factor")
    ap.add_argument("--duration-sec", type=float, default=30.0, help="Duración tras primer pulso (segundos)")
    # Dejamos --emg-blocks para compatibilidad, pero ya no recortamos a NCH; usamos un mapa fijo de 128 canales.
    ap.add_argument("--emg-blocks", type=str, default="1-32,39-70,77-108,115-146",
                    help="(Ignorado para shape final) Rangos 1-based informativos.")
    args = ap.parse_args()

    base = Path(args.base).resolve()
    emg_files = sorted((base / "emg").glob("*.otb+"))
    kin_files = sorted((base / "pose-3d").glob("*.csv"))

    if len(emg_files) != len(kin_files):
        print("ERROR: Number of EMG and kinematics files does not match!", file=sys.stderr)
        sys.exit(1)

    # Etiquetas movimiento (para las claves)
    mov_labels = [
        'M111','M112','M113','M114','M115',
        'M121','M122','M123','M124','M125',
        'M131','M132','M133','M134','M135',
        'M211','M212','M213','M214','M215',
        'M221','M222','M223','M224','M225',
        'M231','M232','M233','M234','M235'
    ]
    if len(mov_labels) < len(emg_files):
        mov_labels += [f"Mx{i+1:03d}" for i in range(len(mov_labels), len(emg_files))]

    # participantInfo
    S000: Dict[str, Any] = {}
    S000["participantInfo"] = {
        "Age": "36y",
        "Dexterity": "21.5s",
        "ForearmPerimeter": "6.25cm",
        "Gender": "Male",
        "Height": "178cm",
        "Injuries": "None",
        "Laterality": "Right"
    }

    fs_kin = 100
    fs_emg = 2000
    target_rows_kin = int(round(args.duration_sec * fs_kin))
    target_rows_emg = int(round(args.duration_sec * fs_emg))

    # KIN y EMG (labels forzadas)
    S000["kin"] = {"fs": fs_kin, "raw": {}, "labels": None}
    emg_lbls = build_emg_labels()
    S000["emg"] = {"fs": fs_emg, "raw": {}, "labels": to_matlab_row_cell(emg_lbls, 128, "emg.labels")}

    # Mapa fijo de 128 canales (0-based). Canales fuera de NCH -> NaN
    fixed_idx_128 = build_fixed_emg_channel_map()

    for i, (emg_path, kin_path) in enumerate(zip(emg_files, kin_files), start=1):
        print(f"Movement {i} of {len(emg_files)} is being loaded")
        mov = mov_labels[i - 1]

        # --- Kinematics ---
        kin_df = pd.read_csv(kin_path)
        kin_df = drop_kinematics_columns_like_matlab(kin_df)

        # Asegurar EXACTAMENTE 63 columnas (trunc/pad de columnas si fuera necesario)
        kin_cols = list(kin_df.columns)
        if len(kin_cols) > 63:
            print(f"[INFO] kin.columns: truncating {len(kin_cols)} -> 63")
            kin_cols = kin_cols[:63]
            kin_df = kin_df.iloc[:, :63]
        elif len(kin_cols) < 63:
            print(f"[INFO] kin.columns: padding {len(kin_cols)} -> 63 with NaN columns")
            for j in range(len(kin_cols), 63):
                kin_df[f"Extra_{j+1}"] = np.nan
            kin_cols = list(kin_df.columns)[:63]
            kin_df = kin_df.iloc[:, :63]

        kin_mat = kin_df.to_numpy(dtype=float)

        # Forzar número de filas = target_rows_kin (trunc/pad con NaN)
        kin_mat = pad_or_trunc_rows(kin_mat, target_rows_kin)
        S000["kin"]["raw"][mov] = kin_mat
        S000["kin"]["labels"] = to_matlab_row_cell(kin_cols, 63, "kin.labels")

        # --- EMG ---
        with tempfile.TemporaryDirectory(dir=base) as tmpdir:
            tmp = Path(tmpdir)
            robust_untar(emg_path, tmp)

            sig_candidates = list(tmp.rglob("*.sig"))
            if not sig_candidates:
                raise FileNotFoundError(f"No *.sig found in extracted {emg_path.name}")
            sig_path = sig_candidates[0]

            # limpiar XMLs auxiliares y leer el device XML
            for p in list(tmp.rglob("form*.xml")) + list(tmp.rglob("patient.xml")):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

            xml_candidates = list(tmp.rglob("*.xml"))
            if not xml_candidates:
                raise FileNotFoundError(f"No XML found in extracted {emg_path.name}")
            xml_path = xml_candidates[0]

            nch, fsamp = parse_device_attrs(xml_path)
            emg_mat_full = read_sig_matrix(sig_path, nch, dtype="<i2")  # [nch, samples]

        # Canal de sincronía (forzado o autodetectado)
        if args.sync_channel is not None:
            sync_idx = args.sync_channel - 1
            if not (0 <= sync_idx < emg_mat_full.shape[0]):
                raise IndexError(f"sync-channel {args.sync_channel} out of bounds for NCH={emg_mat_full.shape[0]}")
        else:
            sync_idx = detect_sync_channel(emg_mat_full, factor=args.peak_factor)

        syncSig = emg_mat_full[sync_idx, :]
        thr = float(np.mean(syncSig)) * float(args.peak_factor)
        peaks, _ = find_peaks(syncSig, height=thr)
        if peaks.size == 0:
            thr = float(np.mean(syncSig)) * max(2.0, args.peak_factor / 2.0)
            peaks, _ = find_peaks(syncSig, height=thr)
        if peaks.size == 0:
            raise RuntimeError(f"No sync peaks found (auto channel {sync_idx+1}) in {emg_path.name}")

        start_sync = int(peaks[0])
        end_sync = start_sync + target_rows_emg - 1
        # recorte a lo disponible
        max_end = emg_mat_full.shape[1] - 1
        if end_sync > max_end:
            print(f"[INFO] EMG window clipped and will be padded: "
                  f"requested end={end_sync}, max available={max_end}")
            end_sync = max_end

        # Construir matriz [samples x 128] con NaN y rellenar lo existente
        samples_slice = slice(start_sync, end_sync + 1)
        emg_slice_len = end_sync - start_sync + 1
        emg_out = np.full((emg_slice_len, 128), np.nan, dtype=float)

        for j, ch_idx in enumerate(fixed_idx_128):
            if 0 <= ch_idx < emg_mat_full.shape[0]:
                emg_out[:, j] = emg_mat_full[ch_idx, samples_slice]
            else:
                # canal deseado no existe en NCH -> se queda NaN
                pass

        # Forzar filas = target_rows_emg (pad con NaN si fue más corto por clip)
        emg_out = pad_or_trunc_rows(emg_out, target_rows_emg)
        S000["emg"]["raw"][mov] = emg_out

        print(f"  NCH={emg_mat_full.shape[0]}, samples={emg_mat_full.shape[1]}, "
              f"sync_ch={sync_idx+1}, window_len={target_rows_emg}, "
              f"emg_out_shape={emg_out.shape}, kin_shape={kin_mat.shape}")

    # Guardar
    S001 = S000
    print("Saving...")
    savemat(str(base / "S001_fixed.mat"), {"S001": S001}, do_compression=True)
    print("Done!")


if __name__ == "__main__":
    main()
