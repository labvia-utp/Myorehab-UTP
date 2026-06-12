#!/usr/bin/env bash
set -Eeuo pipefail

# ========= CONFIG =========
PROJECT_ROOT="$(pwd)"                 # Ejecutar desde la raíz (donde está config.toml)
RECORDING="$PROJECT_ROOT/recording"
MEDIA_PY="$RECORDING/mediapipe_analyze.py"

BASE_ENV="base"                       # Entorno con MediaPipe
ANIPOSE_ENV="anipose"                 # Entorno con Anipose

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline_$(date +"%Y%m%d_%H%M%S").log"

# Redirigir a consola + archivo
exec > >(tee -a "$LOG_FILE") 2>&1

# ========= HELPERS =========
ts()  { date +"%Y-%m-%d %H:%M:%S"; }
log() { printf "\n\033[1;34m[%s INFO]\033[0m %s\n"  "$(ts)" "$*"; }
die() { printf "\n\033[1;31m[%s ERROR]\033[0m %s\n" "$(ts)" "$*" >&2; exit 1; }

req() { command -v "$1" >/dev/null 2>&1 || die "No se encontró '$1' en PATH."; }
ensure_file(){ [[ -f "$1" ]] || die "Falta archivo: $1"; }
ensure_dir(){  [[ -d "$1" ]] || die "Falta carpeta: $1"; }

run(){  # run "Titulo" comando args...
  local title="$1"; shift
  log "$title"
  "$@" || die "Fallo en: $title"
  log "✔ $title — completado."
}

# ========= PRECHECKS =========
log "Log: $LOG_FILE"
req conda
req python
ensure_file "$PROJECT_ROOT/config.toml"
ensure_dir  "$RECORDING"
ensure_file "$MEDIA_PY"

# Entornos conda disponibles
conda env list | awk '{print $1}' | grep -Fxq "$BASE_ENV"    || die "No existe el entorno '$BASE_ENV'."
conda env list | awk '{print $1}' | grep -Fxq "$ANIPOSE_ENV" || die "No existe el entorno '$ANIPOSE_ENV'."

# Verificar 'anipose' dentro de ANIPOSE_ENV
conda run -n "$ANIPOSE_ENV" anipose --version >/dev/null 2>&1 \
  || conda run -n "$ANIPOSE_ENV" python -c "import anipose" 2>/dev/null \
  || die "No se encontró 'anipose' en el entorno '$ANIPOSE_ENV' (instala con: pip install anipose)"

# Aviso si no hay videos en recording/videos-raw (opcional)
if [[ -d "$RECORDING/videos-raw" ]]; then
  n_videos=$(find "$RECORDING/videos-raw" -maxdepth 1 -type f \( -iname "*.mp4" -o -iname "*.avi" -o -iname "*.mov" -o -iname "*.mkv" \) | wc -l | tr -d ' ')
  [[ "$n_videos" -eq 0 ]] && log "Advertencia: 'recording/videos-raw' está vacío."
fi

log "CWD: $PROJECT_ROOT"
log "Python: $(python -V 2>&1 || true)"
log "Conda actual: ${CONDA_DEFAULT_ENV:-<none>}"

log "============ PRE-CHEQUEOS EXITOSOS ============"
log "Todos los entornos, rutas y dependencias están listos para el pipeline."

log "=== INICIO PIPELINE: MediaPipe → Anipose ==="

# ========= 1) MEDIAPIPE (BASE_ENV) =========

(
  cd "$RECORDING"
  run "1) Ejecutando mediapipe_analyze.py (env '$BASE_ENV')" \
    conda run -n "$BASE_ENV" python "$MEDIA_PY"
)

# ========= 2) ANIPOSE (ANIPOSE_ENV) =========

(
  cd "$PROJECT_ROOT"  # anipose busca config.toml en el CWD
  run "2.1) Anipose filter (env '$ANIPOSE_ENV')"      conda run -n "$ANIPOSE_ENV" anipose filter
  run "2.2) Anipose calibrate (env '$ANIPOSE_ENV')"   conda run -n "$ANIPOSE_ENV" anipose calibrate
  run "2.3) Anipose triangulate (env '$ANIPOSE_ENV')" conda run -n "$ANIPOSE_ENV" anipose triangulate
)

log "✅ PIPELINE COMPLETADO. Revisa el log: $LOG_FILE"

# chmod +x automate.sh
# ./automate.sh

# Script utilizado en git bash / Windows Terminal.