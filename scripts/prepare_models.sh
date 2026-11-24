#!/usr/bin/env bash
# ==============================================================================
# NESFIC-I-07: Prepare Drone Models for Dual-UAV Simulation
# Clones iris_with_ardupilot -> iris_sprayer, patches fdm_port_in to 9012
# Usage: chmod +x scripts/prepare_models.sh && ./scripts/prepare_models.sh
# ==============================================================================
set -euo pipefail

echo "==============================================================================="
echo " NESFIC-I-07: Preparing dual-UAV models (Scout + Sprayer)"
echo "==============================================================================="

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
GZ_MODELS_DIR="${HOME}/.gz/sim/models"
ARDUPILOT_GAZEBO_MODELS="${HOME}/ardupilot_gazebo/models"
ARDUPILOT_MODELS="${HOME}/ardupilot/Tools/autotest/models"

# Ensure model directories exist
mkdir -p "${GZ_MODELS_DIR}"

# -----------------------------------------------------------------------------
# 1) Ensure base iris_with_ardupilot exists (from ardupilot_gazebo)
# -----------------------------------------------------------------------------
BASE_MODEL_SRC="${ARDUPILOT_GAZEBO_MODELS}/iris_with_ardupilot"
BASE_MODEL_DST="${GZ_MODELS_DIR}/iris_with_ardupilot"

if [[ ! -d "${BASE_MODEL_SRC}" ]]; then
    echo "ERROR: Base model not found at ${BASE_MODEL_SRC}"
    echo "Run ./scripts/ubuntu_install_sim.sh first to install ardupilot_gazebo"
    exit 1
fi

echo "[1/4] Copying base iris_with_ardupilot to Gazebo model path..."
cp -r "${BASE_MODEL_SRC}" "${BASE_MODEL_DST}"

# -----------------------------------------------------------------------------
# 2) Create iris_scout (uses default fdm_port_in = 9002 from SDF)
# -----------------------------------------------------------------------------
SCOUT_MODEL="${GZ_MODELS_DIR}/iris_scout"
echo "[2/4] Creating iris_scout model (fdm_port_in=9002)..."
cp -r "${BASE_MODEL_DST}" "${SCOUT_MODEL}"

# Update model.config name
sed -i 's/<name>iris_with_ardupilot<\/name>/<name>iris_scout<\/name>/' "${SCOUT_MODEL}/model.config"
sed -i 's/<description>.*<\/description>/<description>NESFIC-I-07 Scout UAV (sysid=1, fdm_port_in=9002)<\/description>/' "${SCOUT_MODEL}/model.config"

# Ensure fdm_port_in is 9002 in model.sdf (already default in base, but enforce)
sed -i 's/<fdm_port_in>[0-9]*<\/fdm_port_in>/<fdm_port_in>9002<\/fdm_port_in>/' "${SCOUT_MODEL}/model.sdf"

# -----------------------------------------------------------------------------
# 3) Create iris_sprayer with fdm_port_in = 9012
# -----------------------------------------------------------------------------
SPRAYER_MODEL="${GZ_MODELS_DIR}/iris_sprayer"
echo "[3/4] Creating iris_sprayer model (fdm_port_in=9012)..."
cp -r "${BASE_MODEL_DST}" "${SPRAYER_MODEL}"

# Update model.config
sed -i 's/<name>iris_with_ardupilot<\/name>/<name>iris_sprayer<\/name>/' "${SPRAYER_MODEL}/model.config"
sed -i 's/<description>.*<\/description>/<description>NESFIC-I-07 Sprayer UAV (sysid=2, fdm_port_in=9012)<\/description>/' "${SPRAYER_MODEL}/model.config"

# Patch fdm_port_in to 9012
sed -i 's/<fdm_port_in>[0-9]*<\/fdm_port_in>/<fdm_port_in>9012<\/fdm_port_in>/' "${SPRAYER_MODEL}/model.sdf"

# -----------------------------------------------------------------------------
# 4) Also copy to ardupilot_gazebo/models for sim_vehicle.py -f gazebo-iris
# -----------------------------------------------------------------------------
echo "[4/4] Linking models for ArduPilot sim_vehicle.py..."
mkdir -p "${ARDUPILOT_GAZEBO_MODELS}/iris_scout"
mkdir -p "${ARDUPILOT_GAZEBO_MODELS}/iris_sprayer"

# Copy model.sdf and model.config to ardupilot_gazebo models (sim_vehicle.py looks here)
cp "${SCOUT_MODEL}/model.sdf" "${ARDUPILOT_GAZEBO_MODELS}/iris_scout/"
cp "${SCOUT_MODEL}/model.config" "${ARDUPILOT_GAZEBO_MODELS}/iris_scout/"
cp "${SPRAYER_MODEL}/model.sdf" "${ARDUPILOT_GAZEBO_MODELS}/iris_sprayer/"
cp "${SPRAYER_MODEL}/model.config" "${ARDUPILOT_GAZEBO_MODELS}/iris_sprayer/"

# Also ensure meshes/media are accessible (symlink or copy)
for model in iris_scout iris_sprayer; do
    src="${GZ_MODELS_DIR}/${model}"
    dst="${ARDUPILOT_GAZEBO_MODELS}/${model}"
    for subdir in meshes media; do
        if [[ -d "${src}/${subdir}" ]]; then
            ln -sfn "${src}/${subdir}" "${dst}/${subdir}" 2>/dev/null || cp -r "${src}/${subdir}" "${dst}/"
        fi
    done
done

# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------
echo ""
echo "==============================================================================="
echo " MODEL PREPARATION COMPLETE"
echo "==============================================================================="
echo ""
echo "Models created:"
echo "  ${GZ_MODELS_DIR}/iris_scout     (fdm_port_in=9002)"
echo "  ${GZ_MODELS_DIR}/iris_sprayer   (fdm_port_in=9012)"
echo ""
echo "Verifying fdm_port_in values:"
grep -H "fdm_port_in" "${GZ_MODELS_DIR}/iris_scout/model.sdf"
grep -H "fdm_port_in" "${GZ_MODELS_DIR}/iris_sprayer/model.sdf"
echo ""
echo "Next: ./scripts/launch_ubuntu_sim.sh"