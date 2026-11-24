'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Wifi, WifiOff, Satellite, Zap, Droplets, AlertTriangle,
  Play, Pause, RotateCcw, Settings, Download, Upload,
  MapPin, Radio, Battery, Gauge, Target, SprayCan,
  Shield, CheckCircle, XCircle, Loader2, Truck,
  ChevronDown, ChevronUp, Info, Terminal,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area,
} from 'recharts';

// ============================================================================
// Types
// ============================================================================
interface Telemetry {
  sysid: number;
  timestamp: number;
  lat: number;
  lon: number;
  alt: number;
  relative_alt: number;
  vx: number;
  vy: number;
  vz: number;
  roll: number;
  pitch: number;
  yaw: number;
  groundspeed: number;
  airspeed: number;
  battery_voltage: number;
  battery_current: number;
  battery_remaining: number;
  mode: string;
  armed: boolean;
  mission_state: string;
  current_wp: number;
  wp_total: number;
  spray_active: boolean;
  spray_servo_pwm: number;
}

interface Hotspot {
  id: string;
  lat: number;
  lon: number;
  center_x: number;
  center_y: number;
  radius_m: number;
  pest_type: string;
  severity: number;
  confidence: number;
  recommended_chemical: string;
  application_rate_ml_per_l: number;
  timestamp: number;
}

interface DockAuditRecord {
  record_id: string;
  section_id: string;
  timestamp: string;
  dock_state: string;
  survey_data: any;
  hotspots: Hotspot[];
  tank_mix: any;
  mrl_verification: any;
  compliance_status: string;
  operator_id: string;
  signature: string;
}

type DockState = 'IDLE' | 'CHARGING' | 'AI_INFERENCE' | 'CHEMICAL_MIXING' | 'LINE_FLUSH' | 'MRL_VERIFICATION' | 'READY_FOR_SORTIE' | 'ERROR';

type MissionState = 'IDLE' | 'ARMING' | 'TAKING_OFF' | 'SURVEYING' | 'SPRAYING' | 'RETURNING' | 'LANDING' | 'DOCKED' | 'ERROR';

// ============================================================================
// Constants
// ============================================================================
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/telemetry';
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

const DOCK_STATE_COLORS: Record<DockState, string> = {
  IDLE: 'text-nesfic-400',
  CHARGING: 'text-accent-cyan',
  AI_INFERENCE: 'text-accent-blue',
  CHEMICAL_MIXING: 'text-accent-purple',
  LINE_FLUSH: 'text-accent-amber',
  MRL_VERIFICATION: 'text-accent-green',
  READY_FOR_SORTIE: 'text-accent-green',
  ERROR: 'text-accent-red',
};

const MISSION_STATE_COLORS: Record<MissionState, string> = {
  IDLE: 'text-nesfic-400',
  ARMING: 'text-accent-amber',
  TAKING_OFF: 'text-accent-blue',
  SURVEYING: 'text-accent-cyan',
  SPRAYING: 'text-accent-purple',
  RETURNING: 'text-accent-green',
  LANDING: 'text-accent-amber',
  DOCKED: 'text-nesfic-400',
  ERROR: 'text-accent-red',
};

const PEST_TYPE_LABELS: Record<string, string> = {
  tea_mosquito_bug: 'Tea Mosquito Bug',
  red_spider_mite: 'Red Spider Mite',
  thrips: 'Thrips',
  aphids: 'Aphids',
  jassids: 'Jassids',
  leaf_roller: 'Leaf Roller',
  yellow_mite: 'Yellow Mite',
  blister_blight: 'Blister Blight',
  grey_blight: 'Grey Blight',
  whitefly: 'Whitefly',
};

const CHEMICAL_LABELS: Record<string, string> = {
  deltamethrin_ec: 'Deltamethrin 2.8% EC',
  thiamethoxam_wg: 'Thiamethoxam 25% WG',
  hexythiazox_wp: 'Hexythiazox 5.45% WP',
  tebuconazole_ec: 'Tebuconazole 25.9% EC',
  spirotetramat_sc: 'Spirotetramat 11.01% SC',
};

// ============================================================================
// Utility Functions
// ============================================================================
function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false });
}

function formatAltitude(alt: number): string {
  return `${alt.toFixed(1)}m`;
}

function formatSpeed(speed: number): string {
  return `${speed.toFixed(1)} m/s`;
}

function formatBattery(v: number, remaining: number): string {
  return `${v.toFixed(1)}V (${remaining.toFixed(0)}%)`;
}

function latLonToMapXY(lat: number, lon: number, centerLat: number, centerLon: number, scale: number): { x: number; y: number } {
  // Simple equirectangular projection for small area
  const latDiff = (lat - centerLat) * 111111; // meters
  const lonDiff = (lon - centerLon) * 111111 * Math.cos(centerLat * Math.PI / 180);
  return {
    x: 250 + lonDiff * scale, // Center at 250,250 (500x500 map)
    y: 250 - latDiff * scale, // Invert Y (North up)
  };
}

// ============================================================================
// Components
// ============================================================================

// Status Indicator Dot
function StatusDot({ connected, className = '' }: { connected: boolean | null; className?: string }) {
  if (connected === null) return <span className={`status-dot disconnected ${className}`} />;
  return <span className={`status-dot ${connected ? 'connected' : 'disconnected'} ${className}`} />;
}

// Metric Card
function MetricCard({ label, value, unit, trend, icon: Icon }: {
  label: string;
  value: string | number;
  unit?: string;
  trend?: 'up' | 'down' | 'stable';
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="glass-card p-4 flex items-center gap-4 animate-in">
      {Icon && <div className="p-2 bg-accent-cyan/10 rounded-xl text-accent-cyan"><Icon className="w-5 h-5" /></div>}
      <div className="flex-1 min-w-0">
        <p className="metric-label">{label}</p>
        <p className="metric-value text-accent-cyan flex items-center gap-2">
          {value}
          {unit && <span className="text-sm font-normal text-nesfic-400">{unit}</span>}
          {trend && (
            <span className={`text-xs ${trend === 'up' ? 'text-accent-green' : trend === 'down' ? 'text-accent-red' : 'text-nesfic-400'}`}>
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

// Telemetry Panel for each UAV
function TelemetryPanel({ title, telemetry, sysid, icon: Icon }: {
  title: string;
  telemetry: Telemetry | null;
  sysid: number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const connected = telemetry !== null && (Date.now() / 1000 - telemetry.timestamp) < 5;

  if (!telemetry) {
    return (
      <div className="glass-card p-4 animate-in">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-nesfic-800/50 rounded-xl text-nesfic-400"><Icon className="w-5 h-5" /></div>
          <div>
            <h3 className="font-semibold text-nesfic-100">{title}</h3>
            <p className="text-xs text-nesfic-500">SysID: {sysid}</p>
          </div>
          <StatusDot connected={null} className="ml-auto" />
        </div>
        <p className="text-nesfic-500 text-center py-8">No telemetry data</p>
      </div>
    );
  }

  return (
    <div className="glass-card p-4 animate-in">
      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 rounded-xl ${telemetry.armed ? 'bg-accent-cyan/10 text-accent-cyan' : 'bg-nesfic-800/50 text-nesfic-400'}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-nesfic-100">{title}</h3>
          <p className="text-xs text-nesfic-500">SysID: {sysid} • Last: {formatTime(telemetry.timestamp)}</p>
        </div>
        <StatusDot connected={connected} className="ml-auto" />
      </div>

      <div className="space-y-3 telemetry-panel">
        <div className="telemetry-row">
          <span className="telemetry-key">MODE</span>
          <span className="telemetry-val px-3 py-1 bg-nesfic-800/50 rounded-lg text-xs font-mono">
            {telemetry.mode}
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">MISSION</span>
          <span className={`telemetry-val px-3 py-1 bg-nesfic-800/50 rounded-lg text-xs ${MISSION_STATE_COLORS[telemetry.mission_state as MissionState] || ''}`}>
            {telemetry.mission_state}
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">POSITION</span>
          <span className="telemetry-val font-mono text-xs">
            {telemetry.lat.toFixed(6)}, {telemetry.lon.toFixed(6)}
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">ALTITUDE</span>
          <span className="telemetry-val">
            {formatAltitude(telemetry.relative_alt)} AGL / {formatAltitude(telemetry.alt)} AMSL
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">SPEED</span>
          <span className="telemetry-val">
            {formatSpeed(telemetry.groundspeed)} GS / {formatSpeed(telemetry.airspeed)} AS
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">ATTITUDE</span>
          <span className="telemetry-val font-mono text-xs">
            R:{telemetry.roll.toFixed(1)}° P:{telemetry.pitch.toFixed(1)}° Y:{telemetry.yaw.toFixed(1)}°
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">
            <Battery className="w-4 h-4 inline-block mr-1" /> BATTERY
          </span>
          <span className="telemetry-val">
            {formatBattery(telemetry.battery_voltage, telemetry.battery_remaining)}
            {telemetry.battery_current > 0 && ` • ${telemetry.battery_current.toFixed(1)}A`}
          </span>
        </div>

        <div className="telemetry-row">
          <span className="telemetry-key">WAYPOINT</span>
          <span className="telemetry-val">
            {telemetry.current_wp >= 0 ? `${telemetry.current_wp + 1} / ${telemetry.wp_total}` : '—'}
          </span>
        </div>

        {sysid === 2 && telemetry.spray_active && (
          <div className="telemetry-row border-t border-glass-border pt-3">
            <span className="telemetry-key flex items-center gap-2 text-accent-purple">
              <SprayCan className="w-4 h-4" /> SPRAY
            </span>
            <span className="telemetry-val text-accent-purple flex items-center gap-2">
              ACTIVE • PWM: {telemetry.spray_servo_pwm}
              <span className={`w-3 h-3 rounded-full animate-blink ${telemetry.spray_servo_pwm > 1500 ? 'bg-accent-cyan' : 'bg-nesfic-600'}`} />
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// Dock Status Panel
function DockPanel({ dockState, hotspots, tankMix, mrlVerification, auditRecord, onProcess, onDownload, processing }: {
  dockState: DockState;
  hotspots: Hotspot[];
  tankMix: any;
  mrlVerification: any;
  auditRecord: DockAuditRecord | null;
  onProcess: () => void;
  onDownload: (format: 'json' | 'csv') => void;
  processing: boolean;
}) {
  const isReady = dockState === 'READY_FOR_SORTIE';
  const isError = dockState === 'ERROR';

  return (
    <div className="glass-card p-4 animate-in">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-accent-purple/10 rounded-xl text-accent-purple"><Truck className="w-5 h-5" /></div>
        <div>
          <h3 className="font-semibold text-nesfic-100">Smart Dock Station</h3>
          <p className="text-xs text-nesfic-500">Automated charging, AI inference, chemical mixing & MRL compliance</p>
        </div>
        <span className={`ml-auto px-3 py-1 rounded-full text-xs font-semibold border ${DOCK_STATE_COLORS[dockState]} border-current/30 bg-current/10`}>
          {dockState.replace('_', ' ')}
        </span>
      </div>

      {/* FSM Progress Steps */}
      <div className="mb-4 space-y-2">
        {[
          { id: 'CHARGING', label: 'Charging', icon: Zap },
          { id: 'AI_INFERENCE', label: 'AI Inference', icon: Radio },
          { id: 'CHEMICAL_MIXING', label: 'Chemical Mixing', icon: Droplets },
          { id: 'LINE_FLUSH', label: 'Line Flush', icon: RotateCcw },
          { id: 'MRL_VERIFICATION', label: 'MRL Verification', icon: Shield },
          { id: 'READY_FOR_SORTIE', label: 'Ready for Sortie', icon: CheckCircle },
        ].map((step, idx) => {
          const stepState = step.id as DockState;
          const isActive = dockState === stepState;
          const isComplete = [
            'CHARGING', 'AI_INFERENCE', 'CHEMICAL_MIXING', 'LINE_FLUSH', 'MRL_VERIFICATION', 'READY_FOR_SORTIE'
          ].indexOf(dockState) > idx;
          const Icon = step.icon;

          return (
            <div key={step.id} className="flex items-center gap-3 text-sm">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium border-2 ${isComplete || isActive ? 'border-accent-cyan bg-accent-cyan/20 text-accent-cyan' : 'border-nesfic-600 text-nesfic-500'}`}>
                {isComplete ? <CheckCircle className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
              </div>
              <div className="flex-1">
                <p className={`${isActive ? 'text-accent-cyan' : isComplete ? 'text-nesfic-300' : 'text-nesfic-500'} font-medium`}>{step.label}</p>
                {isActive && <div className="h-1 bg-accent-cyan/30 rounded-full overflow-hidden"><div className="h-full bg-accent-cyan animate-pulse" style={{ width: '100%' }} /></div>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Hotspots Summary */}
      {hotspots.length > 0 && (
        <div className="mb-4 p-3 bg-nesfic-900/50 rounded-xl border border-glass-border">
          <h4 className="text-sm font-semibold text-nesfic-300 mb-2 flex items-center gap-2">
            <MapPin className="w-4 h-4 text-accent-amber" /> Infested Hotspots ({hotspots.length})
          </h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {hotspots.map((hs) => (
              <div key={hs.id} className="flex items-center gap-2 p-2 bg-nesfic-800/50 rounded-lg">
                <span className="w-2 h-2 rounded-full bg-accent-red" />
                <span className="text-nesfic-300">{PEST_TYPE_LABELS[hs.pest_type] || hs.pest_type}</span>
                <span className="text-nesfic-500 ml-auto">{hs.severity.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tank Mix */}
      {tankMix && (
        <div className="mb-4 p-3 bg-nesfic-900/50 rounded-xl border border-glass-border">
          <h4 className="text-sm font-semibold text-nesfic-300 mb-2 flex items-center gap-2">
            <Droplets className="w-4 h-4 text-accent-cyan" /> Tank Mix: {tankMix.batch_id}
          </h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-nesfic-400">Total Volume</div>
            <div className="text-nesfic-300 font-mono">{(tankMix.total_volume_ml / 1000).toFixed(2)} L</div>
            <div className="text-nesfic-400">Carrier Water</div>
            <div className="text-nesfic-300 font-mono">{(tankMix.carrier_water_ml / 1000).toFixed(2)} L</div>
            <div className="text-nesfic-400">Surfactant</div>
            <div className="text-nesfic-300 font-mono">{(tankMix.surfactant_ml).toFixed(0)} ml</div>
            <div className="text-nesfic-400">Chemicals</div>
            <div className="text-nesfic-300 font-mono">{(Object.values(tankMix.chemicals) as number[]).reduce((a, b) => a + b, 0).toFixed(0)} ml</div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(tankMix.chemicals).map(([key, vol]) => (
              <span key={key} className="px-2 py-1 bg-accent-cyan/10 text-accent-cyan text-xs rounded border border-accent-cyan/20">
                {CHEMICAL_LABELS[key] || key}: {(vol as number).toFixed(0)}ml
              </span>
            ))}
          </div>
        </div>
      )}

      {/* MRL Verification */}
      {mrlVerification && mrlVerification.mrl_details && (
        <div className="mb-4 p-3 bg-nesfic-900/50 rounded-xl border border-glass-border">
          <h4 className="text-sm font-semibold text-nesfic-300 mb-2 flex items-center gap-2">
            <Shield className="w-4 h-4 {mrlVerification.overall_compliant ? 'text-accent-green' : 'text-accent-red'}" /> MRL Compliance
          </h4>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="text-nesfic-400">Parameter</div>
            <div className="text-nesfic-400 text-center">EU</div>
            <div className="text-nesfic-400 text-center">Japan</div>
            {Object.entries(mrlVerification.mrl_details).map(([chem, details]: [string, any]) => (
              <>
                <div className="text-nesfic-300">{chem}</div>
                <div className={`text-center ${details.phi_eu_ok ? 'text-accent-green' : 'text-accent-red'}`}>
                  {details.phi_eu_ok ? '✓' : '✗'} PHI
                </div>
                <div className={`text-center ${details.phi_japan_ok ? 'text-accent-green' : 'text-accent-red'}`}>
                  {details.phi_japan_ok ? '✓' : '✗'} PHI
                </div>
              </>
            ))}
          </div>
          <div className="mt-2 text-xs text-center" style={{ color: mrlVerification.overall_compliant ? '#2ed573' : '#ff4757' }}>
            {mrlVerification.overall_compliant ? 'COMPLIANT ✓' : 'NON-COMPLIANT ✗'}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onProcess}
          disabled={processing || dockState !== 'IDLE'}
          className="btn-primary flex-1 min-w-[140px]"
        >
          <Loader2 className="w-4 h-4 mr-2 animate-spin" style={{ display: processing ? 'block' : 'none' }} />
          {processing ? 'Processing...' : 'Process Mission'}
        </button>

        <button
          onClick={() => onDownload('json')}
          disabled={!auditRecord}
          className="btn-secondary"
        >
          <Download className="w-4 h-4 mr-1" /> JSON
        </button>
        <button
          onClick={() => onDownload('csv')}
          disabled={!auditRecord}
          className="btn-secondary"
        >
          <Download className="w-4 h-4 mr-1" /> CSV
        </button>
      </div>

      {/* Latest Audit Record */}
      {auditRecord && (
        <details className="mt-4 group">
          <summary className="cursor-pointer flex items-center gap-2 text-sm text-nesfic-400 hover:text-nesfic-300">
            <Terminal className="w-4 h-4" /> Latest Audit: {auditRecord.record_id}
            <ChevronDown className="w-4 h-4 ml-auto transition-transform group-open:rotate-180" />
          </summary>
          <pre className="mt-2 p-3 bg-nesfic-900/50 rounded-lg text-xs text-nesfic-300 overflow-x-auto max-h-64">
            {JSON.stringify(auditRecord, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

// Map View Component
function MapView({ scoutTelemetry, sprayerTelemetry, hotspots, dockPosition }: {
  scoutTelemetry: Telemetry | null;
  sprayerTelemetry: Telemetry | null;
  hotspots: Hotspot[];
  dockPosition: { lat: number; lon: number };
}) {
  const mapRef = useRef<HTMLCanvasElement>(null);
  const [scale, setScale] = useState(2.5); // meters per pixel

  // Draw on canvas
  useEffect(() => {
    const canvas = mapRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = 500;
    const height = 500;
    canvas.width = width * 2; // High DPI
    canvas.height = height * 2;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(2, 2);

    const centerLat = dockPosition.lat;
    const centerLon = dockPosition.lon;

    // Clear
    ctx.fillStyle = '#050507';
    ctx.fillRect(0, 0, width, height);

    // Grid
    ctx.strokeStyle = 'rgba(0, 245, 212, 0.04)';
    ctx.lineWidth = 1;
    const gridSize = 20;
    for (let x = 0; x <= width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Section A-14 boundary (60x60m centered at dock)
    const sectionHalf = 30 * scale;
    ctx.strokeStyle = 'rgba(255, 184, 0, 0.5)';
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(
      width / 2 - sectionHalf,
      height / 2 - sectionHalf,
      sectionHalf * 2,
      sectionHalf * 2
    );
    ctx.setLineDash([]);

    // Dock position
    const dockPos = latLonToMapXY(dockPosition.lat, dockPosition.lon, centerLat, centerLon, scale);
    ctx.fillStyle = '#00f5d4';
    ctx.beginPath();
    ctx.arc(dockPos.x, dockPos.y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(0, 245, 212, 0.5)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(dockPos.x, dockPos.y, 14, 0, Math.PI * 2);
    ctx.stroke();

    // Hotspots
    hotspots.forEach((hs) => {
      const pos = latLonToMapXY(hs.lat, hs.lon, centerLat, centerLon, scale);
      const radius = hs.radius_m * scale;

      // Fill
      const gradient = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, radius);
      gradient.addColorStop(0, 'rgba(255, 71, 87, 0.3)');
      gradient.addColorStop(1, 'rgba(255, 71, 87, 0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Border
      ctx.strokeStyle = '#ff4757';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = '#ff4757';
      ctx.font = 'bold 11px "Space Grotesk"';
      ctx.textAlign = 'center';
      ctx.fillText(PEST_TYPE_LABELS[hs.pest_type] || hs.pest_type, pos.x, pos.y - radius - 6);
    });

    // Scout UAV
    if (scoutTelemetry) {
      const pos = latLonToMapXY(scoutTelemetry.lat, scoutTelemetry.lon, centerLat, centerLon, scale);
      const yaw = scoutTelemetry.yaw;

      // Trail (simplified - just current position)
      ctx.fillStyle = '#00f5d4';
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 10, 0, Math.PI * 2);
      ctx.fill();

      // Heading indicator
      ctx.strokeStyle = '#00f5d4';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      ctx.lineTo(
        pos.x + Math.sin(yaw) * 20,
        pos.y - Math.cos(yaw) * 20
      );
      ctx.stroke();

      // Label
      ctx.fillStyle = '#00f5d4';
      ctx.font = '11px "Space Grotesk"';
      ctx.textAlign = 'center';
      ctx.fillText('SCOUT', pos.x, pos.y + 22);
    }

    // Sprayer UAV
    if (sprayerTelemetry) {
      const pos = latLonToMapXY(sprayerTelemetry.lat, sprayerTelemetry.lon, centerLat, centerLon, scale);
      const yaw = sprayerTelemetry.yaw;

      // Sprayer icon (diamond)
      ctx.fillStyle = sprayerTelemetry.spray_active ? '#a55eea' : '#ffb800';
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y - 10);
      ctx.lineTo(pos.x + 10, pos.y);
      ctx.lineTo(pos.x, pos.y + 10);
      ctx.lineTo(pos.x - 10, pos.y);
      ctx.closePath();
      ctx.fill();

      // Spray effect
      if (sprayerTelemetry.spray_active) {
        ctx.fillStyle = 'rgba(165, 94, 234, 0.3)';
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 25, 0, Math.PI * 2);
        ctx.fill();
      }

      // Heading
      ctx.strokeStyle = sprayerTelemetry.spray_active ? '#a55eea' : '#ffb800';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      ctx.lineTo(
        pos.x + Math.sin(yaw) * 20,
        pos.y - Math.cos(yaw) * 20
      );
      ctx.stroke();

      // Label
      ctx.fillStyle = sprayerTelemetry.spray_active ? '#a55eea' : '#ffb800';
      ctx.font = '11px "Space Grotesk"';
      ctx.textAlign = 'center';
      ctx.fillText('SPRAYER', pos.x, pos.y + 22);
    }

    // Legend
    ctx.font = '10px "Space Grotesk"';
    ctx.textAlign = 'left';
    let legendY = 20;
    const legendItems = [
      { color: '#00f5d4', label: 'Scout UAV' },
      { color: '#ffb800', label: 'Sprayer UAV (idle)' },
      { color: '#a55eea', label: 'Sprayer UAV (spraying)' },
      { color: '#ff4757', label: 'Infested Hotspot' },
      { color: '#00f5d4', label: 'Smart Dock', dash: true },
    ];

    legendItems.forEach((item) => {
      ctx.fillStyle = item.color;
      if (item.dash) {
        ctx.setLineDash([4, 2]);
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(12, legendY - 2);
        ctx.lineTo(24, legendY - 2);
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.beginPath();
        ctx.arc(18, legendY - 2, 4, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = '#888';
      ctx.fillText(item.label, 30, legendY + 1);
      legendY += 18;
    });
  }, [scoutTelemetry, sprayerTelemetry, hotspots, dockPosition, scale]);

  return (
    <div className="glass-card relative overflow-hidden" style={{ width: 500, height: 500 }}>
      <canvas ref={mapRef} className="w-full h-full" />
      <div className="absolute bottom-4 left-4 right-4 flex justify-between items-end p-4 pointer-events-none">
        <div className="text-xs text-nesfic-400">
          Scale: ~{Math.round(100 / scale)}m/px • Section A-14: 60×60m
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setScale(s => Math.min(5, s + 0.5))}
            className="btn-secondary text-xs px-3 py-1"
            title="Zoom In"
          >+</button>
          <button
            onClick={() => setScale(s => Math.max(0.5, s - 0.5))}
            className="btn-secondary text-xs px-3 py-1"
            title="Zoom Out"
          >−</button>
        </div>
      </div>
    </div>
  );
}

// Battery History Chart
function BatteryChart({ telemetry }: { telemetry: Telemetry | null }) {
  const [history, setHistory] = useState<Array<{ time: string; voltage: number; remaining: number }>>([]);

  useEffect(() => {
    if (!telemetry) return;
    setHistory(prev => [...prev.slice(-59), {
      time: formatTime(telemetry.timestamp),
      voltage: telemetry.battery_voltage,
      remaining: telemetry.battery_remaining,
    }]);
  }, [telemetry]);

  if (history.length < 2) return <div className="h-48 flex items-center justify-center text-nesfic-500">Waiting for data...</div>;

  return (
    <div className="glass-card p-4 h-64">
      <h4 className="text-sm font-semibold text-nesfic-300 mb-4 flex items-center gap-2">
        <Battery className="w-4 h-4 text-accent-cyan" /> Battery History (60s)
      </h4>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={history} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="voltageGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00f5d4" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#00f5d4" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="remainingGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ffb800" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#ffb800" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" vertical={false} />
          <XAxis
            dataKey="time"
            tick={{ fill: '#666', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="left"
            orientation="left"
            tick={{ fill: '#00f5d4', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            domain={[20, 25]}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: '#ffb800', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            domain={[0, 100]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0a0a12',
              border: '1px solid rgba(0, 245, 212, 0.2)',
              borderRadius: '8px',
            }}
            formatter={(value: number, name: string) => [
              name === 'voltage' ? `${value.toFixed(1)}V` : `${value.toFixed(0)}%`,
              name === 'voltage' ? 'Voltage' : 'Remaining',
            ]}
          />
          <Area
            yAxisId="left"
            type="monotone"
            dataKey="voltage"
            stroke="#00f5d4"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#voltageGradient)"
          />
          <Area
            yAxisId="right"
            type="monotone"
            dataKey="remaining"
            stroke="#ffb800"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#remainingGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// Altitude Chart
function AltitudeChart({ scoutTelemetry, sprayerTelemetry }: {
  scoutTelemetry: Telemetry | null;
  sprayerTelemetry: Telemetry | null;
}) {
  type AltitudePoint = {
    time: string;
    scoutAlt: number | null;
    sprayerAlt: number | null;
  };

  const [history, setHistory] = useState<AltitudePoint[]>([]);

  useEffect(() => {
    const scoutAlt = scoutTelemetry?.relative_alt ?? null;
    const sprayerAlt = sprayerTelemetry?.relative_alt ?? null;
    if (scoutAlt === null && sprayerAlt === null) return;

    setHistory((prev: AltitudePoint[]) => [...prev.slice(-59), {
      time: formatTime(Date.now() / 1000),
      scoutAlt,
      sprayerAlt,
    }]);
  }, [scoutTelemetry, sprayerTelemetry]);

  if (history.length < 2) return <div className="h-48 flex items-center justify-center text-nesfic-500">Waiting for data...</div>;

  return (
    <div className="glass-card p-4 h-64">
      <h4 className="text-sm font-semibold text-nesfic-300 mb-4 flex items-center gap-2">
        <Gauge className="w-4 h-4 text-accent-cyan" /> Altitude AGL (60s)
      </h4>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={history} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" vertical={false} />
          <XAxis
            dataKey="time"
            tick={{ fill: '#666', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#888', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            domain={[0, 'auto']}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0a0a12',
              border: '1px solid rgba(0, 245, 212, 0.2)',
              borderRadius: '8px',
            }}
            formatter={(value: number) => [`${value.toFixed(1)}m`, 'Altitude']}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="scoutAlt"
            stroke="#00f5d4"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            name="Scout"
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="sprayerAlt"
            stroke="#ffb800"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            activeDot={{ r: 4 }}
            name="Sprayer"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Mission Control Panel
function MissionControl({ onScoutStart, onScoutRTL, onSprayerStart, onSprayerRTL, dockReady, scoutState, sprayerState }: {
  onScoutStart: () => void;
  onScoutRTL: () => void;
  onSprayerStart: () => void;
  onSprayerRTL: () => void;
  dockReady: boolean;
  scoutState: MissionState;
  sprayerState: MissionState;
}) {
  return (
    <div className="glass-card p-4 animate-in">
      <h3 className="font-semibold text-nesfic-100 mb-4 flex items-center gap-2">
        <Target className="w-5 h-5 text-accent-cyan" /> Mission Control
      </h3>

      {/* Scout Controls */}
      <div className="mb-4 p-3 bg-nesfic-900/50 rounded-xl border border-glass-border">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-medium text-nesfic-300 flex items-center gap-2">
            <Satellite className="w-4 h-4 text-accent-cyan" /> Scout UAV (Survey)
          </h4>
          <span className={`px-2 py-1 rounded-full text-xs font-semibold ${MISSION_STATE_COLORS[scoutState]}`}>
            {scoutState}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onScoutStart}
            disabled={scoutState !== 'IDLE' && scoutState !== 'DOCKED' && scoutState !== 'ERROR'}
            className="btn-primary flex-1"
          >
            <Play className="w-4 h-4 mr-2" /> Start Survey
          </button>
          <button
            onClick={onScoutRTL}
            disabled={scoutState === 'IDLE' || scoutState === 'DOCKED' || scoutState === 'RETURNING'}
            className="btn-secondary"
          >
            <RotateCcw className="w-4 h-4 mr-2" /> RTL
          </button>
        </div>
      </div>

      {/* Sprayer Controls */}
      <div className="p-3 bg-nesfic-900/50 rounded-xl border border-glass-border">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-medium text-nesfic-300 flex items-center gap-2">
            <SprayCan className="w-4 h-4 text-accent-purple" /> Sprayer UAV (Spot-Spray)
          </h4>
          <span className={`px-2 py-1 rounded-full text-xs font-semibold ${MISSION_STATE_COLORS[sprayerState]}`}>
            {sprayerState}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onSprayerStart}
            disabled={!dockReady || sprayerState !== 'IDLE' && sprayerState !== 'DOCKED' && sprayerState !== 'ERROR'}
            className="btn-primary flex-1"
          >
            <SprayCan className="w-4 h-4 mr-2" /> Start Spot-Spray
          </button>
          <button
            onClick={onSprayerRTL}
            disabled={sprayerState === 'IDLE' || sprayerState === 'DOCKED' || sprayerState === 'RETURNING'}
            className="btn-secondary"
          >
            <RotateCcw className="w-4 h-4 mr-2" /> RTL
          </button>
        </div>
        {!dockReady && (
          <p className="text-xs text-nesfic-500 mt-2 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Dock not ready — run <code className="px-1 bg-nesfic-800 rounded">/dock/process</code> first
          </p>
        )}
      </div>
    </div>
  );
}

// Log Panel
function LogPanel({ logs }: { logs: string[] }) {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="glass-card p-4 flex-1 min-h-[200px] flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-nesfic-100 flex items-center gap-2">
          <Terminal className="w-5 h-5 text-accent-cyan" /> System Log
        </h3>
        <span className="text-xs text-nesfic-500">{logs.length} entries</span>
      </div>
      <div ref={logRef} className="flex-1 overflow-y-auto font-mono text-xs text-nesfic-300 bg-nesfic-900/50 rounded-xl p-3 space-y-1">
        {logs.map((log, i) => (
          <div key={i} className="border-l-2 border-nesfic-700 pl-2 py-0.5">
            <span className="text-nesfic-500">[{new Date().toLocaleTimeString()}]</span>{' '}
            <span className="text-nesfic-400">{log}</span>
          </div>
        ))}
        {logs.length === 0 && <p className="text-nesfic-600 text-center py-8">No log entries yet</p>}
      </div>
    </div>
  );
}

// ============================================================================
// Main Dashboard
// ============================================================================
export default function Dashboard() {
  // State
  const [scoutTelemetry, setScoutTelemetry] = useState<Telemetry | null>(null);
  const [sprayerTelemetry, setSprayerTelemetry] = useState<Telemetry | null>(null);
  const [dockState, setDockState] = useState<DockState>('IDLE');
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [tankMix, setTankMix] = useState<any>(null);
  const [mrlVerification, setMrlVerification] = useState<any>(null);
  const [auditRecord, setAuditRecord] = useState<DockAuditRecord | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [daysToHarvest, setDaysToHarvest] = useState(14);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const addLog = useCallback((msg: string) => {
    setLogs(prev => [...prev.slice(-99), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  // WebSocket Connection
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        addLog('WebSocket connected to telemetry stream');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'telemetry' && msg.data) {
            const tel = msg.data as Telemetry;
            if (tel.sysid === 1) {
              setScoutTelemetry(tel);
            } else if (tel.sysid === 2) {
              setSprayerTelemetry(tel);
            }
          } else if (msg.type === 'initial_state') {
            if (msg.scout) setScoutTelemetry(msg.scout);
            if (msg.sprayer) setSprayerTelemetry(msg.sprayer);
            if (msg.dock_state) setDockState(msg.dock_state);
            addLog('Received initial state from server');
          }
        } catch (e) {
          console.error('WS parse error:', e);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        addLog('WebSocket disconnected, reconnecting in 3s...');
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = (err) => {
        addLog(`WebSocket error: ${err}`);
      };
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [addLog]);

  // API Calls
  const handleScoutStart = async () => {
    try {
      addLog('Starting Scout survey mission...');
      const res = await fetch(`${API_BASE}/mission/scout/start`, { method: 'POST' });
      const data = await res.json();
      addLog(`Scout mission started: ${data.mission}`);
    } catch (e) {
      addLog(`Scout start failed: ${e}`);
    }
  };

  const handleScoutRTL = async () => {
    try {
      addLog('Commanding Scout RTL...');
      await fetch(`${API_BASE}/mission/scout/rtl`, { method: 'POST' });
      addLog('Scout RTL commanded');
    } catch (e) {
      addLog(`Scout RTL failed: ${e}`);
    }
  };

  const handleDockProcess = async () => {
    setProcessing(true);
    try {
      addLog(`Processing dock mission (PHI: ${daysToHarvest}d)...`);
      const res = await fetch(`${API_BASE}/dock/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days_to_harvest: daysToHarvest }),
      });
      const data = await res.json();
      setDockState(data.compliance_status === 'COMPLIANT' ? 'READY_FOR_SORTIE' : 'ERROR');
      setHotspots(data.hotspots_count > 0 ? [] : []); // Will be populated from audit
      setTankMix(data.tank_mix);
      setMrlVerification(data.mrl_verification);
      addLog(`Dock processing complete: ${data.compliance_status} (${data.hotspots_count} hotspots)`);

      // Fetch latest audit
      const auditRes = await fetch(`${API_BASE}/audit/latest`);
      const audit = await auditRes.json();
      setAuditRecord(audit);
      if (audit.hotspots) setHotspots(audit.hotspots);
      if (audit.tank_mix) setTankMix(audit.tank_mix);
      if (audit.mrl_verification) setMrlVerification(audit.mrl_verification);
    } catch (e) {
      addLog(`Dock process failed: ${e}`);
      setDockState('ERROR');
    } finally {
      setProcessing(false);
    }
  };

  const handleSprayerStart = async () => {
    try {
      addLog('Starting Sprayer spot-spray mission...');
      const res = await fetch(`${API_BASE}/mission/sprayer/start`, { method: 'POST' });
      const data = await res.json();
      addLog(`Sprayer mission started: ${data.hotspots} hotspots, batch ${data.tank_mix_batch}`);
    } catch (e) {
      addLog(`Sprayer start failed: ${e}`);
    }
  };

  const handleSprayerRTL = async () => {
    try {
      addLog('Commanding Sprayer RTL...');
      await fetch(`${API_BASE}/mission/sprayer/rtl`, { method: 'POST' });
      addLog('Sprayer RTL commanded');
    } catch (e) {
      addLog(`Sprayer RTL failed: ${e}`);
    }
  };

  const handleDownload = async (format: 'json' | 'csv') => {
    try {
      addLog(`Downloading audit log (${format.toUpperCase()})...`);
      const res = await fetch(`${API_BASE}/audit/export?format=${format}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_log.${format}`;
      a.click();
      window.URL.revokeObjectURL(url);
      addLog('Download complete');
    } catch (e) {
      addLog(`Download failed: ${e}`);
    }
  };

  // Dock position (Tocklai approx)
  const dockPosition = { lat: 26.7300, lon: 94.2300 };

  return (
    <div className="min-h-screen bg-nesfic-950">
      {/* Background glow */}
      <div className="fixed inset-0 bg-radial-glow pointer-events-none" aria-hidden="true" />

      {/* Header */}
      <header className="border-b border-nesfic-800 bg-nesfic-950/80 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-accent-cyan/10 rounded-xl text-accent-cyan">
              <Satellite className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-nesfic-100">NESFIC-I-07</h1>
              <p className="text-xs text-nesfic-500">Tea Drone PoW Dashboard • Tocklai TRA</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Connection Status */}
            <div className="flex items-center gap-2 px-3 py-1.5 bg-nesfic-900/50 rounded-xl border border-glass-border">
              <StatusDot connected={wsConnected} />
              <span className="text-sm font-mono text-nesfic-300">
                {wsConnected ? 'LIVE' : 'OFFLINE'}
              </span>
            </div>

            {/* Days to Harvest Selector */}
            <div className="flex items-center gap-2 px-3 py-1.5 bg-nesfic-900/50 rounded-xl border border-glass-border">
              <label className="text-xs text-nesfic-400">PHI (days):</label>
              <select
                value={daysToHarvest}
                onChange={(e) => setDaysToHarvest(Number(e.target.value))}
                className="input-field w-auto px-3 py-1.5 text-sm bg-nesfic-800"
              >
                {[7, 10, 14, 21, 28].map(d => (
                  <option key={d} value={d}>{d} days</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <main className="max-w-7xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: Map + Telemetry */}
        <div className="lg:col-span-7 space-y-4">
          {/* Map */}
          <MapView
            scoutTelemetry={scoutTelemetry}
            sprayerTelemetry={sprayerTelemetry}
            hotspots={hotspots}
            dockPosition={dockPosition}
          />

          {/* Telemetry Panels */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TelemetryPanel
              title="Scout UAV"
              telemetry={scoutTelemetry}
              sysid={1}
              icon={Satellite}
            />
            <TelemetryPanel
              title="Sprayer UAV"
              telemetry={sprayerTelemetry}
              sysid={2}
              icon={SprayCan}
            />
          </div>
        </div>

        {/* Right Column: Dock + Controls + Charts */}
        <div className="lg:col-span-5 space-y-4">
          {/* Dock Panel */}
          <DockPanel
            dockState={dockState}
            hotspots={hotspots}
            tankMix={tankMix}
            mrlVerification={mrlVerification}
            auditRecord={auditRecord}
            onProcess={handleDockProcess}
            onDownload={handleDownload}
            processing={processing}
          />

          {/* Mission Control */}
          <MissionControl
            onScoutStart={handleScoutStart}
            onScoutRTL={handleScoutRTL}
            onSprayerStart={handleSprayerStart}
            onSprayerRTL={handleSprayerRTL}
            dockReady={dockState === 'READY_FOR_SORTIE'}
            scoutState={scoutTelemetry?.mission_state as MissionState || 'IDLE'}
            sprayerState={sprayerTelemetry?.mission_state as MissionState || 'IDLE'}
          />

          {/* Charts */}
          <div className="grid grid-cols-1 gap-4">
            <BatteryChart telemetry={scoutTelemetry || sprayerTelemetry} />
            <AltitudeChart scoutTelemetry={scoutTelemetry} sprayerTelemetry={sprayerTelemetry} />
          </div>
        </div>

        {/* Bottom: Log Panel (full width) */}
        <div className="lg:col-span-12">
          <LogPanel logs={logs} />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-nesfic-800 bg-nesfic-950/80 backdrop-blur-xl px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs text-nesfic-500">
          <span>NESFIC-I-07 • Tea Research Association, Tocklai • PoW Simulation</span>
          <span>ArduPilot SITL + Gazebo Harmonic • FastAPI + Next.js 14</span>
        </div>
      </footer>
    </div>
  );
}