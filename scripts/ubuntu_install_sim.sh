#!/usr/bin/env bash
# ==============================================================================
# NESFIC-I-07: Ubuntu One-Shot Installer for ArduPilot SITL + Gazebo Harmonic
# Target: Ubuntu 22.04 / 24.04
# Usage: chmod +x scripts/ubuntu_install_sim.sh && ./scripts/ubuntu_install_sim.sh
# ==============================================================================
set -euo pipefail

echo "==============================================================================="
echo " NESFIC-I-07: Installing ArduPilot SITL + Gazebo Harmonic + ardupilot_gazebo"
echo "==============================================================================="

# -----------------------------------------------------------------------------
# System update & base dependencies
# -----------------------------------------------------------------------------
echo "[1/7] Updating apt and installing base dependencies..."
sudo apt-get update -y
sudo apt-get install -y \
    git curl wget lsb-release gnupg2 software-properties-common \
    build-essential cmake ninja-build pkg-config \
    python3 python3-pip python3-venv python3-dev \
    libxml2-dev libxslt1-dev zlib1g-dev libssl-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    protobuf-compiler libprotobuf-dev \
    libignition-math6-dev libignition-msgs-dev libignition-transport-dev \
    libsdformat-dev libgz-sim-dev libgz-msgs-dev libgz-transport-dev \
    libgz-common-dev libgz-utils-dev

# -----------------------------------------------------------------------------
# Gazebo Harmonic (Gazebo Garden/Gazebo 8) via OSRF packages
# -----------------------------------------------------------------------------
echo "[2/7] Adding Gazebo Harmonic repository..."
sudo wget -q https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/gazebo-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gazebo-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
    | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt-get update -y

echo "[3/7] Installing Gazebo Harmonic..."
sudo apt-get install -y gz-harmonic

# -----------------------------------------------------------------------------
# ArduPilot SITL dependencies & source build
# -----------------------------------------------------------------------------
echo "[4/7] Installing ArduPilot dependencies..."
sudo apt-get install -y \
    python3-future python3-lxml python3-pip python3-yaml python3-matplotlib \
    python3-numpy python3-scipy python3-pymavlink python3-pyx \
    python3-pygame python3-tk python3-dev python3-setuptools python3-wheel \
    libjpeg-dev libpng-dev libfreetype6-dev liblcms2-dev libwebp-dev \
    libopenjp2-7-dev libtiff-dev libharfbuzz-dev libfribidi-dev \
    libxcb1-dev libx11-dev libxext-dev libxrender-dev libxi-dev \
    libxrandr-dev libxxf86vm-dev libgl1-mesa-dev libglu1-mesa-dev \
    libglew-dev libglfw3-dev libassimp-dev libtinyxml2-dev \
    libeigen3-dev libboost-all-dev

# -----------------------------------------------------------------------------
# Clone ArduPilot (shallow for speed) and build SITL
# -----------------------------------------------------------------------------
echo "[5/7] Cloning ArduPilot source..."
ARDUPILOT_DIR="${HOME}/ardupilot"
if [[ ! -d "${ARDUPILOT_DIR}" ]]; then
    git clone --depth 1 --branch master https://github.com/ArduPilot/ardupilot.git "${ARDUPILOT_DIR}"
else
    echo "ArduPilot already exists at ${ARDUPILOT_DIR}, updating..."
    cd "${ARDUPILOT_DIR}" && git pull --ff-only
fi

echo "[6/7] Building ArduPilot SITL (this may take 10-20 minutes)..."
cd "${ARDUPILOT_DIR}"
./Tools/environment_install/install-prereqs-ubuntu.sh -y || true
./waf configure --board sitl
./waf copter

# -----------------------------------------------------------------------------
# ardupilot_gazebo plugin (Gazebo Harmonic compatible)
# -----------------------------------------------------------------------------
echo "[7/7] Installing ardupilot_gazebo plugin..."
ARDUPILOT_GAZEBO_DIR="${HOME}/ardupilot_gazebo"
if [[ ! -d "${ARDUPILOT_GAZEBO_DIR}" ]]; then
    git clone --depth 1 --branch harmonic https://github.com/ArduPilot/ardupilot_gazebo.git "${ARDUPILOT_GAZEBO_DIR}"
else
    echo "ardupilot_gazebo already exists, updating..."
    cd "${ARDUPILOT_GAZEBO_DIR}" && git pull --ff-only
fi

cd "${ARDUPILOT_GAZEBO_DIR}"
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install

# -----------------------------------------------------------------------------
# Environment setup for Gazebo model paths
# -----------------------------------------------------------------------------
echo "Configuring Gazebo model paths..."
GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-${HOME}/.gz/sim}"
mkdir -p "${GZ_SIM_RESOURCE_PATH}/worlds"
mkdir -p "${GZ_SIM_RESOURCE_PATH}/models"

# Add to bashrc if not present
BASHRC="${HOME}/.bashrc"
grep -q "GZ_SIM_RESOURCE_PATH" "${BASHRC}" 2>/dev/null || {
    cat >> "${BASHRC}" <<'EOF'

# NESFIC-I-07: Gazebo Harmonic + ArduPilot SITL paths
export GZ_SIM_RESOURCE_PATH="${HOME}/.gz/sim:${HOME}/ardupilot_gazebo/models:${HOME}/ardupilot/Tools/autotest/models"
export PATH="${HOME}/ardupilot/Tools/autotest:${PATH}"
export ARDUPILOT_GAZEBO_MODEL_PATH="${HOME}/ardupilot_gazebo/models"
EOF
}

# Source for current session
export GZ_SIM_RESOURCE_PATH="${HOME}/.gz/sim:${HOME}/ardupilot_gazebo/models:${HOME}/ardupilot/Tools/autotest/models"
export PATH="${HOME}/ardupilot/Tools/autotest:${PATH}"
export ARDUPILOT_GAZEBO_MODEL_PATH="${HOME}/ardupilot_gazebo/models"

# -----------------------------------------------------------------------------
# Python packages for backend
# -----------------------------------------------------------------------------
echo "Installing Python backend dependencies..."
cd "${HOME}/nesfic-tea-drone-pow/backend" 2>/dev/null || true
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Frontend dependencies
# -----------------------------------------------------------------------------
echo "Installing frontend dependencies..."
cd "${HOME}/nesfic-tea-drone-pow/frontend" 2>/dev/null || true
npm ci

echo ""
echo "==============================================================================="
echo " INSTALLATION COMPLETE"
echo "==============================================================================="
echo ""
echo "Next steps:"
echo "  1) source ~/.bashrc   (or open a new terminal)"
echo "  2) ./scripts/prepare_models.sh"
echo "  3) ./scripts/launch_ubuntu_sim.sh"
echo ""
echo "Manual verification commands:"
echo "  gazebo --version                 # Should show Gazebo Harmonic (8.x)"
echo "  sim_vehicle.py --help            # ArduPilot SITL"
echo "  gz sim --versions                # Gazebo transport versions"
echo ""