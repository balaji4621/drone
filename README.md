# NESFIC-I-07: Tea Research Association — Drone PoW Simulation & Telemetry System

**Project**: AI-Driven Drone-Based Pest Detection & Targeted Spot-Spraying for Assam & Dooars Tea Plantations  
**Repository**: `github.com/balaji4621/nesfic-tea-drone-pow`  
**Cross-OS Development**: Authored on **Windows 11 (VS Code)** → Pushed to GitHub → Cloned on **Ubuntu** for **ArduPilot SITL + Gazebo Harmonic** execution.

---

## 🎯 System Architecture (Fixed Port Contract)

| Component | Instance | Port / Address | Purpose |
|-----------|----------|----------------|---------|
| **Scout UAV** (sysid=1) | ArduPilot `-I 0` | Gazebo FDM: `9002` → MAVLink: `udp:127.0.0.1:14550` | Lawnmower survey @ 12m AGL over Section A-14 (60m×60m) |
| **Sprayer UAV** (sysid=2) | ArduPilot `-I 1` | Gazebo FDM: `9012` → MAVLink: `udp:127.0.0.1:14560` | Spot-spray @ 6m AGL, 4s hover + servo pulse (ch9 PWM 1900/1100) |
| **Smart Dock** | Local Origin `(0,0,0)` | Backend REST: `http://127.0.0.1:8000` | Charging, edge AI inference, chemical mixing, MRL audit logger |
| **Backend API** | FastAPI + WebSocket | `http://127.0.0.1:8000` / `ws://127.0.0.1:8000/ws/telemetry` | Fleet telemetry, mission control, audit export |
| **Frontend** | Next.js 14 + Tailwind | `http://127.0.0.1:3000` | Ultra-dark glassmorphic dashboard |

---

## 📁 Repository Structure

```
nesfic-tea-drone-pow/
├── .gitattributes              # eol=lf enforcement (CRITICAL cross-OS)
├── .gitignore
├── README.md
├── scripts/
│   ├── ubuntu_install_sim.sh   # One-shot Ubuntu installer (ArduPilot SITL + Gazebo Harmonic)
│   ├── prepare_models.sh       # Clones iris_with_ardupilot → iris_sprayer, patches fdm_port_in
│   └── launch_ubuntu_sim.sh    # Launches Gazebo + 2×SITL + Backend + Frontend
├── world/
│   └── tea_estate_2drones.sdf  # Gazebo Harmonic world: 100m×100m tea block, dock, 3 infested patches
├── backend/
│   ├── requirements.txt
│   ├── config.py               # Ports, coordinates, TRA chemical & EU/Japan MRL rulebook
│   ├── mavlink_fleet.py        # Dual-UAV MAVLink controller + 10Hz physics mock fallback
│   ├── pest_detector.py        # ONNX Runtime edge CV + deterministic tile analyzer
│   ├── dock_engine.py          # Smart Dock FSM + chemical mixing + MRL audit exporter
│   └── main.py                 # FastAPI REST + WebSocket (/ws/telemetry)
├── frontend/                   # Next.js 14 (App Router, TypeScript, Tailwind)
└── audit_logs/
    └── .gitkeep                # JSON + CSV section-wise infestation & spray audit records
```

---

## ✅ Prerequisites

### Windows 11 (Authoring & Verification)
- Python 3.11+
- Node.js 20+
- Git (with `core.autocrlf=input` recommended)
- VS Code

### Ubuntu 22.04 / 24.04 (Execution Target)
- ArduPilot SITL
- Gazebo Harmonic
- `ardupilot_gazebo` plugin
- Python 3.10+ with `pip`
- Node.js 20+ with `npm`

---

## 🚀 Quick Start

### 1️⃣ On Windows (Author, Verify, Push)

```powershell
# Clone or navigate to workspace
cd C:\Users\ADMIN\OneDrive\Desktop\drone

# Verify Python syntax on all backend modules
python -m py_compile backend\config.py backend\mavlink_fleet.py backend\pest_detector.py backend\dock_engine.py backend\main.py

# Verify shell scripts have LF endings
git ls-files --eol scripts/*.sh

# Install frontend deps & type-check (optional, requires Node)
cd frontend && npm ci && npm run build && cd ..

# Initialize git & push to GitHub
git init
git add .
git commit -m "Initial commit: NESFIC-I-07 PoW simulation"
git branch -M main
git remote add origin https://github.com/balaji4621/nesfic-tea-drone-pow.git
git push -u origin main
```

### 2️⃣ On Ubuntu (Clone & Run Simulation)

```bash
# Clone the repository
git clone https://github.com/balaji4621/nesfic-tea-drone-pow.git
cd nesfic-tea-drone-pow

# Make scripts executable
chmod +x scripts/*.sh

# One-shot install of ArduPilot SITL, Gazebo Harmonic, and ardupilot_gazebo
./scripts/ubuntu_install_sim.sh

# Prepare drone models (Scout + Sprayer with correct fdm_port_in)
./scripts/prepare_models.sh

# Launch the full simulation stack:
#   - Gazebo Harmonic world (tea_estate_2drones.sdf)
#   - Scout SITL (-I 0, fdm_port_in=9002, MAVLink out=14550)
#   - Sprayer SITL (-I 1, fdm_port_in=9012, MAVLink out=14560)
#   - Backend FastAPI + WebSocket (port 8000)
#   - Frontend Next.js (port 3000)
./scripts/launch_ubuntu_sim.sh
```

---

## 🔧 Manual Step-by-Step (Ubuntu) — If Auto-Launch Fails

```bash
# 1) Start Gazebo Harmonic with the tea estate world
gazebo world/tea_estate_2drones.sdf --verbose

# 2) In NEW terminal: Start Scout SITL (sysid=1, -I 0)
cd ~/ardupilot/ArduCopter
sim_vehicle.py -v ArduCopter -f gazebo-iris --console --map \
  -I 0 --model JSON \
  --out=udp:127.0.0.1:14550 \
  --add-param-file=../Tools/autotest/default_params/copter.parm \
  -D

# 3) In NEW terminal: Start Sprayer SITL (sysid=2, -I 1)
cd ~/ardupilot/ArduCopter
sim_vehicle.py -v ArduCopter -f gazebo-iris --console --map \
  -I 1 --model JSON \
  --out=udp:127.0.0.1:14560 \
  --add-param-file=../Tools/autotest/default_params/copter.parm \
  -D

# 4) In NEW terminal: Start Backend
cd ~/nesfic-tea-drone-pow/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5) In NEW terminal: Start Frontend
cd ~/nesfic-tea-drone-pow/frontend
npm ci
npm run dev
```

---

## 🖥️ Frontend Development (Windows)

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build        # Production build verification
npm run lint         # ESLint check
```

---

## 📡 Backend API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/config` | Port & coordinate config |
| `GET` | `/telemetry/scout` | Latest Scout MAVLink telemetry |
| `GET` | `/telemetry/sprayer` | Latest Sprayer MAVLink telemetry |
| `POST` | `/mission/scout/start` | Launch Scout lawnmower survey |
| `POST` | `/mission/sprayer/start` | Launch Sprayer spot-spray (after Dock ready) |
| `POST` | `/dock/process` | Trigger Dock AI inference + chemical mixing + MRL check |
| `GET` | `/audit/latest` | Latest audit log (JSON) |
| `GET` | `/audit/export?format=csv` | Export audit as CSV |
| `WS` | `/ws/telemetry` | Real-time telemetry stream (both UAVs) |

---

## 🧪 Verification Checklist

- [ ] All `.sh`, `.py`, `.sdf`, `.json`, `.ts`, `.tsx` files use **LF (`\n`)** line endings (`git ls-files --eol`)
- [ ] `python -m py_compile` passes on all backend modules
- [ ] `npm run build` passes on frontend
- [ ] Gazebo launches without SDF parse errors
- [ ] Both SITL instances connect to Gazebo (FDM ports 9002, 9012)
- [ ] MAVLink telemetry received on UDP 14550 (Scout) and 14560 (Sprayer)
- [ ] Backend `/health` returns 200
- [ ] WebSocket `/ws/telemetry` streams JSON telemetry
- [ ] Frontend renders ultra-dark glassmorphic dashboard at `localhost:3000`
- [ ] Audit logs written to `audit_logs/` as JSON + CSV

---

## 🛡️ EU & Japan MRL Compliance

The Smart Dock (`dock_engine.py`) enforces pre-harvest interval (PHI) and maximum residue limits (MRL) per:

| Regulation | Scope | Key Constraints |
|------------|-------|-----------------|
| **EU Regulation 396/2005** | All tea exports to EU | PHI ≥ 7 days for approved actives; MRL lookup via EU Pesticides Database |
| **Japan Positive List System** | All tea exports to Japan | PHI ≥ 14 days; Default MRL 0.01 mg/kg for unlisted substances |

Chemical mixing logic validates:
- Active ingredient concentration ≤ label max
- Tank mix compatibility (no precipitation)
- Surfactant dose within 0.05–0.1% v/v
- Total volume ≤ 10L (Sprayer payload limit)
- PHI compliance before `RTL` authorization

---

## 📄 License & Attribution

**Tea Research Association, Tocklai** — NESFIC-I-07 Proof-of-Work  
Internal use only. Not for redistribution without written consent.

---

## 🆘 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gazebo: command not found` | Run `./scripts/ubuntu_install_sim.sh` |
| `sim_vehicle.py: not found` | Source ArduPilot venv: `source ~/ardupilot/venv/bin/activate` |
| `Address already in use: 14550` | Kill stale `sim_vehicle.py` processes: `pkill -f sim_vehicle` |
| Frontend shows blank page | `cd frontend && rm -rf .next node_modules && npm ci && npm run dev` |
| WebSocket connection refused | Ensure backend running on `0.0.0.0:8000`, not `127.0.0.1:8000` |
| CRLF line ending errors on Ubuntu | `git config core.autocrlf input` then re-clone, or run `dos2unix` on affected files |

---

*Built for NESFIC-I-07 • Tea Research Association, Tocklai • Cross-OS PoW Simulation*