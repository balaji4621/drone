"""
NESFIC-I-07: Pest Detection Module
- Edge CV detector (ONNX Runtime ready)
- Deterministic tea-block tile analyzer (ground truth from SDF)
- Outputs georeferenced infestation hotspots for Sprayer sortie
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from config import GEOMETRY, TRA_CHEMICALS


# =============================================================================
# Data Structures
# =============================================================================
@dataclass
class InfestationHotspot:
    """Georeferenced infestation hotspot for targeted spraying."""
    id: str
    center_x: float  # Local NED North (m)
    center_y: float  # Local NED East (m)
    radius_m: float
    pest_type: str
    severity: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    recommended_chemical: str  # Key into TRA_CHEMICALS
    application_rate_ml_per_l: float
    timestamp: float = field(default_factory=time.time)

    def to_latlon(self, home_lat: float, home_lon: float) -> tuple[float, float]:
        """Convert local NED to lat/lon."""
        lat = home_lat + (self.center_x / 111111.0)
        lon = home_lon + (self.center_y / (111111.0 * math.cos(math.radians(home_lat))))
        return lat, lon

    def to_dict(self, home_lat: float, home_lon: float) -> dict:
        lat, lon = self.to_latlon(home_lat, home_lon)
        return {
            "id": self.id,
            "lat": lat,
            "lon": lon,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "radius_m": self.radius_m,
            "pest_type": self.pest_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "recommended_chemical": self.recommended_chemical,
            "application_rate_ml_per_l": self.application_rate_ml_per_l,
            "timestamp": self.timestamp,
        }


@dataclass
class SurveyTile:
    """Single tile from Scout lawnmower survey."""
    tile_x: int  # Grid index
    tile_y: int
    center_x: float  # Local NED
    center_y: float
    pest_detected: bool
    pest_type: Optional[str]
    severity: float
    confidence: float
    raw_inference: dict = field(default_factory=dict)


# =============================================================================
# Deterministic Tile Analyzer (Ground Truth from SDF)
# =============================================================================
class DeterministicTileAnalyzer:
    """
    Analyzes Scout survey tiles against known infested patches (from SDF world).
    Used for reproducible testing and CI without real CV model.
    """

    # Ground truth patches from tea_estate_2drones.sdf
    INFESTED_PATCHES = [
        {"cx": -10.0, "cy": -10.0, "radius": 5.0, "pest": "tea_mosquito_bug", "severity": 0.8},
        {"cx": 15.0, "cy": 20.0, "radius": 4.0, "pest": "red_spider_mite", "severity": 0.9},
        {"cx": 40.0, "cy": -20.0, "radius": 6.0, "pest": "thrips", "severity": 0.7},
    ]

    # Pest-to-chemical mapping (TRA recommendations)
    PEST_CHEMICAL_MAP = {
        "tea_mosquito_bug": ("deltamethrin_ec", 200.0),  # ml/L
        "red_spider_mite": ("hexythiazox_wp", 150.0),
        "thrips": ("spirotetramat_sc", 100.0),
        "aphids": ("thiamethoxam_wg", 80.0),
        "jassids": ("thiamethoxam_wg", 80.0),
        "leaf_roller": ("deltamethrin_ec", 200.0),
        "yellow_mite": ("hexythiazox_wp", 150.0),
        "blister_blight": ("tebuconazole_ec", 250.0),
        "grey_blight": ("tebuconazole_ec", 250.0),
        "whitefly": ("spirotetramat_sc", 100.0),
    }

    def __init__(self, tile_size_m: float = GEOMETRY.TILE_SIZE_M):
        self.tile_size = tile_size_m
        self._tile_cache: dict[tuple[int, int], SurveyTile] = {}

    def analyze_tile(self, tile_x: int, tile_y: int, center_x: float, center_y: float) -> SurveyTile:
        """
        Deterministic analysis: check if tile center falls within any infested patch.
        """
        cache_key = (tile_x, tile_y)
        if cache_key in self._tile_cache:
            return self._tile_cache[cache_key]

        pest_detected = False
        pest_type = None
        severity = 0.0
        confidence = 0.0

        for patch in self.INFESTED_PATCHES:
            dx = center_x - patch["cx"]
            dy = center_y - patch["cy"]
            dist = math.hypot(dx, dy)

            if dist <= patch["radius"]:
                pest_detected = True
                pest_type = patch["pest"]
                # Severity falls off at patch edge
                severity = patch["severity"] * (1.0 - dist / patch["radius"])
                confidence = 0.85 + 0.1 * (1.0 - dist / patch["radius"])
                break

        tile = SurveyTile(
            tile_x=tile_x,
            tile_y=tile_y,
            center_x=center_x,
            center_y=center_y,
            pest_detected=pest_detected,
            pest_type=pest_type,
            severity=severity,
            confidence=confidence,
            raw_inference={"method": "deterministic_sdf_ground_truth"},
        )

        self._tile_cache[cache_key] = tile
        return tile

    def generate_survey_grid(self) -> list[SurveyTile]:
        """
        Generate all tiles for Section A-14 lawnmower survey.
        Returns tiles in survey order (lawnmower pattern).
        """
        tiles = []
        spacing = self.tile_size
        x_start = GEOMETRY.MIN_X
        x_end = GEOMETRY.MAX_X
        y_start = GEOMETRY.MIN_Y
        y_end = GEOMETRY.MAX_Y

        tile_x = 0
        toggle = True
        y = y_start
        while y <= y_end:
            if toggle:
                x_range = range(int((x_end - x_start) / spacing) + 1)
            else:
                x_range = range(int((x_end - x_start) / spacing), -1, -1)

            for i in x_range:
                cx = x_start + i * spacing + spacing / 2
                cy = y + spacing / 2
                tile = self.analyze_tile(tile_x, int((y - y_start) / spacing), cx, cy)
                tiles.append(tile)
                tile_x += 1

            y += spacing
            toggle = not toggle

        return tiles


# =============================================================================
# ONNX Runtime Edge CV Detector (Production)
# =============================================================================
class ONNXPestDetector:
    """
    ONNX Runtime inference for tea pest detection.
    Expects model with input: (1, 3, 224, 224), output: (num_classes,) logits.
    """

    def __init__(self, model_path: str | Path, class_names: list[str], input_size: tuple[int, int] = (224, 224)):
        self.model_path = Path(model_path)
        self.class_names = class_names
        self.input_size = input_size
        self._session: Optional[object] = None
        self._input_name: Optional[str] = None
        self._output_name: Optional[str] = None

    def load(self) -> bool:
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name
            return True
        except Exception as e:
            print(f"[ONNXPestDetector] Failed to load model: {e}")
            return False

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Resize, normalize to ImageNet stats, CHW format."""
        import cv2
        img = cv2.resize(image, self.input_size)
        img = img.astype(np.float32) / 255.0
        # ImageNet normalization
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # Add batch dim
        return img

    def infer(self, image: np.ndarray) -> tuple[str, float, np.ndarray]:
        """
        Returns (predicted_class, confidence, all_logits).
        """
        if self._session is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        input_tensor = self.preprocess(image)
        outputs = self._session.run([self._output_name], {self._input_name: input_tensor})
        logits = outputs[0][0]
        probs = self._softmax(logits)
        idx = int(np.argmax(probs))
        return self.class_names[idx], float(probs[idx]), probs

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()


# =============================================================================
# High-level Pest Detection Service
# =============================================================================
class PestDetectionService:
    """
    Orchestrates tile analysis and hotspot clustering for Sprayer sortie planning.
    """

    def __init__(self, use_onnx: bool = False, onnx_model_path: str | Path | None = None):
        self.use_onnx = use_onnx
        self.deterministic = DeterministicTileAnalyzer()
        self.onnx_detector: Optional[ONNXPestDetector] = None

        if use_onnx and onnx_model_path:
            # Default class names for tea pests
            class_names = [
                "tea_mosquito_bug", "red_spider_mite", "thrips", "aphids",
                "jassids", "leaf_roller", "yellow_mite", "blister_blight",
                "grey_blight", "whitefly", "healthy"
            ]
            self.onnx_detector = ONNXPestDetector(onnx_model_path, class_names)
            self.onnx_detector.load()

        self._survey_tiles: list[SurveyTile] = []
        self._hotspots: list[InfestationHotspot] = []

    def process_scout_survey(self, tiles: Optional[list[SurveyTile]] = None) -> list[SurveyTile]:
        """
        Process Scout survey tiles. If tiles not provided, generate from deterministic analyzer.
        """
        if tiles is None:
            tiles = self.deterministic.generate_survey_grid()
        self._survey_tiles = tiles
        return tiles

    def cluster_hotspots(self, min_severity: float = 0.1, merge_radius_m: float = 8.0) -> list[InfestationHotspot]:
        """
        Cluster adjacent pest-detected tiles into hotspots.
        """
        if not self._survey_tiles:
            return []

        # Filter pest-detected tiles
        pest_tiles = [t for t in self._survey_tiles if t.pest_detected and t.severity >= min_severity]

        if not pest_tiles:
            self._hotspots = []
            return []

        # Simple clustering: group tiles by pest type and proximity
        clusters: list[list[SurveyTile]] = []
        for tile in pest_tiles:
            assigned = False
            for cluster in clusters:
                # Check if same pest type and close to cluster center
                cluster_pest = cluster[0].pest_type
                if tile.pest_type != cluster_pest:
                    continue
                cx = sum(t.center_x for t in cluster) / len(cluster)
                cy = sum(t.center_y for t in cluster) / len(cluster)
                if math.hypot(tile.center_x - cx, tile.center_y - cy) <= merge_radius_m:
                    cluster.append(tile)
                    assigned = True
                    break
            if not assigned:
                clusters.append([tile])

        # Create hotspots from clusters
        hotspots = []
        for i, cluster in enumerate(clusters):
            pest_type = cluster[0].pest_type
            cx = sum(t.center_x for t in cluster) / len(cluster)
            cy = sum(t.center_y for t in cluster) / len(cluster)
            avg_severity = sum(t.severity for t in cluster) / len(cluster)
            avg_confidence = sum(t.confidence for t in cluster) / len(cluster)
            # Radius covers cluster extent + buffer
            max_dist = max(math.hypot(t.center_x - cx, t.center_y - cy) for t in cluster)
            radius = max_dist + self.deterministic.tile_size

            chem_key, app_rate = self.deterministic.PEST_CHEMICAL_MAP.get(pest_type, ("deltamethrin_ec", 200.0))

            hotspot = InfestationHotspot(
                id=f"hotspot_{i}_{pest_type}",
                center_x=cx,
                center_y=cy,
                radius_m=radius,
                pest_type=pest_type,
                severity=avg_severity,
                confidence=avg_confidence,
                recommended_chemical=chem_key,
                application_rate_ml_per_l=app_rate,
            )
            hotspots.append(hotspot)

        self._hotspots = hotspots
        return hotspots

    def get_sprayer_waypoints(self, home_lat: float, home_lon: float) -> list[tuple[float, float]]:
        """
        Returns (lat, lon) waypoints for Sprayer sortie: dock -> hotspots -> dock.
        """
        if not self._hotspots:
            return [(home_lat, home_lon)]

        waypoints = [(home_lat, home_lon)]  # Start at dock
        for hs in self._hotspots:
            waypoints.append(hs.to_latlon(home_lat, home_lon))
        waypoints.append((home_lat, home_lon))  # Return to dock
        return waypoints

    def get_hotspots_dict(self, home_lat: float, home_lon: float) -> list[dict]:
        return [hs.to_dict(home_lat, home_lon) for hs in self._hotspots]

    def export_audit_record(self, section_id: str = "A-14") -> dict:
        """Export survey + hotspot data for audit logging."""
        return {
            "section_id": section_id,
            "survey_timestamp": time.time(),
            "tiles_total": len(self._survey_tiles),
            "tiles_infested": sum(1 for t in self._survey_tiles if t.pest_detected),
            "hotspots": [hs.to_dict(26.7300, 94.2300) for hs in self._hotspots],  # Tocklai approx coords
            "chemicals_recommended": list(set(hs.recommended_chemical for hs in self._hotspots)),
        }


# =============================================================================
# Singleton Instance
# =============================================================================
_pest_service: Optional[PestDetectionService] = None


def get_pest_service(use_onnx: bool = False, onnx_model_path: str | Path | None = None) -> PestDetectionService:
    global _pest_service
    if _pest_service is None:
        _pest_service = PestDetectionService(use_onnx=use_onnx, onnx_model_path=onnx_model_path)
    return _pest_service