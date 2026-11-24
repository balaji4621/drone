#!/usr/bin/env bash
# ==============================================================================
# NESFIC-I-07: Launch Full Dual-UAV Simulation Stack
# Launches: Gazebo Harmonic + Scout SITL (-I 0) + Sprayer SITL (-I 1) + Backend + Frontend
# Usage: chmod +x scripts/launch_ubuntu_sim.sh && ./scripts/launch_ubuntu_sim.sh
# ==============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PROJECT_ROOT="${HOME}/nesfic-tea-drone-pow"
WORLD_FILE="${PROJECT_ROOT}/world/tea_estate_2drones.sdf"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

# Process tracking
PIDS=()
CLEANUP_DONE=false

cleanup() {
    if [[ "${CLEANUP_DONE}" == "true" ]]; then
        return
    fi
    CLEANUP_DONE=true
    echo ""
    echo "==============================================================================="
    echo " Shutting down simulation stack..."
    echo "==============================================================================="
    for pid in "${PIDS[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill -TERM "${pid}" 2>/dev/null || true
        fi
    done
    # Also kill any stray sim_vehicle.py processes
    pkill -f "sim_vehicle.py.*-I 0" 2>/dev/null || true
    pkill -f "sim_vehicle.py.*-I 1" 2>/dev/null || true
    pkill -f "gazebo.*tea_estate_2drones" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "All processes terminated."
}
trap cleanup EXIT INT TERM

# -----------------------------------------------------------------------------
# Helper: wait for port to be available
# -----------------------------------------------------------------------------
wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="${3:-30}"
    local start_time
    start_time=$(date +%s)
    while ! nc -z "${host}" "${port}" 2>/dev/null; do
        if (( $(date +%s) - start_time > timeout )); then
            echo "TIMEOUT: Port ${port} on ${host} not ready after ${timeout}s"
            return 1
        fi
        sleep 0.5
    done
}

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
echo "==============================================================================="
echo " NESFIC-I-07: Launching Dual-UAV Simulation Stack"
echo "==============================================================================="
echo ""

# Check world file exists
if [[ ! -f "${WORLD_FILE}" ]]; then
    echo "ERROR: World file not found: ${WORLD_FILE}"
    exit 1
fi

# Check models exist
for model in iris_scout iris_sprayer; do
    if [[ ! -d "${HOME}/.gz/sim/models/${model}" ]]; then
        echo "ERROR: Model ${model} not found. Run ./scripts/prepare_models.sh first"
        exit 1
    fi
done

# -----------------------------------------------------------------------------
# 1) Start Gazebo Harmonic
# -----------------------------------------------------------------------------
echo "[1/5] Starting Gazebo Harmonic with tea_estate_2drones.sdf..."
cd "${PROJECT_ROOT}"
gz sim "${WORLD_FILE}" --verbose &
GAZEBO_PID=$!
PIDS+=("${GAZEBO_PID}")
echo "    Gazebo PID: ${GAZEBO_PID}"

# Wait for Gazebo to fully start (give it time to load models and physics)
sleep 5

# -----------------------------------------------------------------------------
# 2) Start Scout SITL (-I 0, fdm_port_in=9002, MAVLink out=14550)
# -----------------------------------------------------------------------------
echo "[2/5] Starting Scout SITL (sysid=1, -I 0)..."
cd "${HOME}/ardupilot/ArduCopter"
sim_vehicle.py -v ArduCopter -f gazebo-iris --console --map \
    -I 0 --model JSON \
    --out=udp:127.0.0.1:14550 \
    --add-param-file=../Tools/autotest/default_params/copter.parm \
    -D &
SCOUT_PID=$!
PIDS+=("${SCOUT_PID}")
echo "    Scout SITL PID: ${SCOUT_PID}"

# -----------------------------------------------------------------------------
# 3) Start Sprayer SITL (-I 1, fdm_port_in=9012, MAVLink out=14560)
# -----------------------------------------------------------------------------
echo "[3/5] Starting Sprayer SITL (sysid=2, -I 1)..."
sim_vehicle.py -v ArduCopter -f gazebo-iris --console --map \
    -I 1 --model JSON \
    --out=udp:127.0.0.1:14560 \
    --add-param-file=../Tools/autotest/default_params/copter.parm \
    -D &
SPRAYER_PID=$!
PIDS+=("${SPRAYER_PID}")
echo "    Sprayer SITL PID: ${SPRAYER_PID}"

# Wait for SITL instances to connect to Gazebo (FDM ports)
echo "    Waiting for FDM connections (ports 9002, 9012)..."
wait_for_port 127.0.0.1 9002 60
wait_for_port 127.0.0.1 9012 60
echo "    FDM connections established."

# -----------------------------------------------------------------------------
# 4) Start Backend (FastAPI + WebSocket)
# -----------------------------------------------------------------------------
echo "[4/5] Starting Backend API (FastAPI on :8000)..."
cd "${BACKEND_DIR}"
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
PIDS+=("${BACKEND_PID}")
echo "    Backend PID: ${BACKEND_PID}"

# Wait for backend health
wait_for_port 127.0.0.1 8000 30
echo "    Backend health check passed."

# -----------------------------------------------------------------------------
# 5) Start Frontend (Next.js)
# -----------------------------------------------------------------------------
echo "[5/5] Starting Frontend (Next.js on :3000)..."
cd "${FRONTEND_DIR}"
npm run dev &
FRONTEND_PID=$!
PIDS+=("${FRONTEND_PID}")
echo "    Frontend PID: ${FRONTEND_PID}"

# Wait for frontend
wait_for_port 127.0.0.1 3000 60
echo "    Frontend ready."

# -----------------------------------------------------------------------------
# All services running - print status
# -----------------------------------------------------------------------------
echo ""
echo "==============================================================================="
echo " SIMULATION STACK RUNNING"
echo "==============================================================================="
echo ""
echo "Services:"
echo "  Gazebo Harmonic      : PID ${GAZEBO_PID}   (world: tea_estate_2drones.sdf)"
echo "  Scout SITL (sysid=1) : PID ${SCOUT_PID}   (MAVLink: udp:127.0.0.1:14550)"
echo "  Sprayer SITL(sysid=2): PID ${SPRAYER_PID}  (MAVLink: udp:127.0.0.1:14560)"
echo "  Backend API          : PID ${BACKEND_PID}   (http://127.0.0.1:8000)"
echo "  Frontend             : PID ${FRONTEND_PID}   (http://127.0.0.1:3000)"
echo ""
echo "WebSocket Telemetry: ws://127.0.0.1:8000/ws/telemetry"
echo ""
echo "Press Ctrl+C to stop all services."
echo "==============================================================================="

# Keep script running until interrupted
wait