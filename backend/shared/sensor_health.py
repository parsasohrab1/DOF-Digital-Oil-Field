"""
Sensor Health Monitoring and Drift Detection
Automated detection of sensor drift and data correction before ML models
"""
import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SensorHealthStatus:
    """Sensor health status"""

    sensor_id: str
    health_score: float  # 0.0 (unhealthy) to 1.0 (healthy)
    drift_detected: bool
    drift_magnitude: float
    calibration_needed: bool
    last_calibration: Optional[datetime]
    data_quality: str  # "good", "degraded", "poor", "failed"
    corrected_value: Optional[float] = None
    correction_applied: bool = False


class SensorDriftDetector:
    """
    Detects sensor drift using statistical methods
    """

    def __init__(self, window_size: int = 1000, drift_threshold: float = 0.1):
        """
        Args:
            window_size: Number of recent readings to analyze
            drift_threshold: Threshold for drift detection (10% by default)
        """
        self.window_size = window_size
        self.drift_threshold = drift_threshold
        self.sensor_history: Dict[str, deque] = {}
        self.baseline_values: Dict[str, float] = {}
        self.calibration_dates: Dict[str, datetime] = {}

    def add_reading(self, sensor_id: str, value: float, timestamp: datetime):
        """Add a sensor reading to history"""
        if sensor_id not in self.sensor_history:
            self.sensor_history[sensor_id] = deque(maxlen=self.window_size)

        self.sensor_history[sensor_id].append({"value": value, "timestamp": timestamp})

    def detect_drift(self, sensor_id: str, current_value: float) -> Tuple[bool, float]:
        """
        Detect sensor drift

        Returns:
            (drift_detected, drift_magnitude)
        """
        if (
            sensor_id not in self.sensor_history
            or len(self.sensor_history[sensor_id]) < 10
        ):
            return False, 0.0

        history = list(self.sensor_history[sensor_id])
        values = [h["value"] for h in history]

        # Calculate baseline (median of first 20% of data)
        baseline_size = max(10, len(values) // 5)
        baseline = np.median(values[:baseline_size])

        # Store baseline if not set
        if sensor_id not in self.baseline_values:
            self.baseline_values[sensor_id] = baseline

        # Calculate current deviation from baseline
        baseline_value = self.baseline_values[sensor_id]
        if baseline_value == 0:
            drift_magnitude = abs(current_value - baseline_value)
        else:
            drift_magnitude = abs((current_value - baseline_value) / baseline_value)

        drift_detected = drift_magnitude > self.drift_threshold

        return drift_detected, drift_magnitude

    def correct_drift(self, sensor_id: str, value: float) -> float:
        """
        Correct sensor value based on detected drift

        Returns:
            Corrected value
        """
        if sensor_id not in self.baseline_values:
            return value

        baseline = self.baseline_values[sensor_id]
        drift_detected, drift_magnitude = self.detect_drift(sensor_id, value)

        if drift_detected:
            # Simple correction: adjust towards baseline
            # In production, use more sophisticated correction algorithms
            correction_factor = 1.0 - (drift_magnitude * 0.5)  # Partial correction
            corrected = baseline + (value - baseline) * correction_factor
            logger.info(
                f"Corrected sensor {sensor_id}: {value} -> {corrected} (drift: {drift_magnitude:.2%})"
            )
            return corrected

        return value

    def update_baseline(self, sensor_id: str, new_baseline: float):
        """Update baseline after calibration"""
        self.baseline_values[sensor_id] = new_baseline
        self.calibration_dates[sensor_id] = datetime.utcnow()
        logger.info(f"Updated baseline for sensor {sensor_id}: {new_baseline}")


class SensorHealthMonitor:
    """
    Comprehensive sensor health monitoring
    """

    def __init__(self):
        self.drift_detector = SensorDriftDetector()
        self.health_scores: Dict[str, float] = {}
        self.last_health_check: Dict[str, datetime] = {}

    def assess_health(
        self,
        sensor_id: str,
        value: float,
        timestamp: datetime,
        expected_range: Optional[Tuple[float, float]] = None,
    ) -> SensorHealthStatus:
        """
        Assess sensor health and detect drift

        Args:
            sensor_id: Sensor identifier
            value: Current sensor value
            timestamp: Reading timestamp
            expected_range: Expected value range (min, max)

        Returns:
            SensorHealthStatus
        """
        # Add reading to history
        self.drift_detector.add_reading(sensor_id, value, timestamp)

        # Detect drift
        drift_detected, drift_magnitude = self.drift_detector.detect_drift(
            sensor_id, value
        )

        # Calculate health score
        health_score = 1.0

        # Reduce score based on drift
        if drift_detected:
            health_score -= min(0.5, drift_magnitude * 2)  # Max 50% reduction

        # Check if value is in expected range
        if expected_range:
            min_val, max_val = expected_range
            if value < min_val or value > max_val:
                health_score -= 0.3  # 30% reduction for out-of-range

        health_score = max(0.0, health_score)

        # Determine data quality
        if health_score >= 0.9:
            data_quality = "good"
        elif health_score >= 0.7:
            data_quality = "degraded"
        elif health_score >= 0.5:
            data_quality = "poor"
        else:
            data_quality = "failed"

        # Correct value if drift detected
        corrected_value = None
        correction_applied = False
        if drift_detected and health_score < 0.8:
            corrected_value = self.drift_detector.correct_drift(sensor_id, value)
            correction_applied = True

        # Check if calibration is needed
        calibration_needed = drift_detected and drift_magnitude > 0.2  # 20% drift

        status = SensorHealthStatus(
            sensor_id=sensor_id,
            health_score=health_score,
            drift_detected=drift_detected,
            drift_magnitude=drift_magnitude,
            calibration_needed=calibration_needed,
            last_calibration=self.drift_detector.calibration_dates.get(sensor_id),
            data_quality=data_quality,
            corrected_value=corrected_value,
            correction_applied=correction_applied,
        )

        self.health_scores[sensor_id] = health_score
        self.last_health_check[sensor_id] = timestamp

        return status

    def get_health_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get health summary for all sensors"""
        summary = {}
        for sensor_id, health_score in self.health_scores.items():
            drift_detected, drift_magnitude = self.drift_detector.detect_drift(
                sensor_id,
                self.drift_detector.sensor_history[sensor_id][-1]["value"]
                if sensor_id in self.drift_detector.sensor_history
                and self.drift_detector.sensor_history[sensor_id]
                else 0,
            )

            summary[sensor_id] = {
                "health_score": health_score,
                "drift_detected": drift_detected,
                "drift_magnitude": drift_magnitude,
                "last_check": self.last_health_check.get(sensor_id),
                "calibration_needed": drift_detected and drift_magnitude > 0.2,
            }

        return summary


# Global instance
sensor_health_monitor = SensorHealthMonitor()
