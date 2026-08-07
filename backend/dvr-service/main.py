"""
Data Validation & Reconciliation (DVR) Service
Real-time data validation, outlier detection, missing data imputation, and reconciliation
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import numpy as np

# Add backend directory to path
backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, backend_dir)

from shared.config import settings
from shared.logging_config import setup_logging
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.auth import require_authentication, require_roles
from shared.database import get_timescale_db, get_db
from shared.models import SensorData, Tag
from sqlalchemy.orm import Session

# Setup logging
logger = setup_logging("dvr-service")

app = FastAPI(title="OGIM DVR Service", version="1.0.0")
setup_metrics(app, "dvr-service")
setup_tracing(app, "dvr-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ValidationRule(BaseModel):
    """Data validation rule"""

    rule_id: str
    sensor_id: str
    rule_type: str  # range, rate_of_change, statistical, completeness
    parameters: Dict[str, Any]
    enabled: bool = True


class ValidationResult(BaseModel):
    """Validation result"""

    sensor_id: str
    timestamp: datetime
    value: float
    is_valid: bool
    validation_score: float  # 0.0 to 1.0
    violations: List[str]
    quality_metrics: Dict[str, Any]


class ReconciliationRequest(BaseModel):
    """Data reconciliation request"""

    sensor_ids: List[str]
    start_time: datetime
    end_time: datetime
    reconciliation_method: str = (
        "statistical"  # statistical, interpolation, model_based
    )


class ReconciliationResult(BaseModel):
    """Reconciliation result"""

    sensor_id: str
    original_value: float
    reconciled_value: float
    reconciliation_method: str
    confidence: float
    timestamp: datetime


class OutlierDetectionRequest(BaseModel):
    """Outlier detection request"""

    sensor_id: str
    window_size: int = 100
    method: str = "zscore"  # zscore, iqr, isolation_forest


class OutlierResult(BaseModel):
    """Outlier detection result"""

    sensor_id: str
    timestamp: datetime
    value: float
    is_outlier: bool
    outlier_score: float
    method: str


class DataQualityScore(BaseModel):
    """Data quality score"""

    sensor_id: str
    quality_score: float  # 0.0 to 1.0
    completeness: float
    accuracy: float
    timeliness: float
    consistency: float
    validity: float
    timestamp: datetime


class StatisticalOutlierDetector:
    """Statistical outlier detection"""

    @staticmethod
    def detect_zscore(values: List[float], threshold: float = 3.0) -> List[bool]:
        """Detect outliers using Z-score"""
        if len(values) < 3:
            return [False] * len(values)

        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return [False] * len(values)

        z_scores = np.abs((values - mean) / std)
        return (z_scores > threshold).tolist()

    @staticmethod
    def detect_iqr(values: List[float]) -> List[bool]:
        """Detect outliers using IQR method"""
        if len(values) < 4:
            return [False] * len(values)

        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        if iqr == 0:
            return [False] * len(values)

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        return [(v < lower_bound or v > upper_bound) for v in values]


class DataReconciler:
    """Data reconciliation algorithms"""

    @staticmethod
    def reconcile_statistical(
        values: List[float], timestamps: List[datetime]
    ) -> List[float]:
        """Statistical reconciliation using moving average"""
        if len(values) < 3:
            return values

        window_size = min(5, len(values) // 2)
        reconciled = []

        for i in range(len(values)):
            start = max(0, i - window_size)
            end = min(len(values), i + window_size + 1)
            window_values = values[start:end]
            reconciled.append(np.mean(window_values))

        return reconciled

    @staticmethod
    def reconcile_interpolation(
        values: List[float], timestamps: List[datetime], missing_indices: List[int]
    ) -> List[float]:
        """Interpolation-based reconciliation"""
        reconciled = values.copy()

        for idx in missing_indices:
            if idx == 0:
                reconciled[idx] = values[1] if len(values) > 1 else 0
            elif idx == len(values) - 1:
                reconciled[idx] = values[-2] if len(values) > 1 else 0
            else:
                # Linear interpolation
                reconciled[idx] = (values[idx - 1] + values[idx + 1]) / 2

        return reconciled


class DataValidator:
    """Real-time data validation"""

    def __init__(self):
        self.validation_rules: Dict[str, List[ValidationRule]] = {}
        self.outlier_detector = StatisticalOutlierDetector()
        self.reconciler = DataReconciler()

    def validate(
        self,
        sensor_id: str,
        value: float,
        timestamp: datetime,
        tag: Optional[Tag] = None,
    ) -> ValidationResult:
        """Validate a single data point"""
        violations = []
        validation_score = 1.0

        # Range validation
        if tag:
            if tag.valid_range_min is not None and value < tag.valid_range_min:
                violations.append(
                    f"Value below minimum: {value} < {tag.valid_range_min}"
                )
                validation_score -= 0.3

            if tag.valid_range_max is not None and value > tag.valid_range_max:
                violations.append(
                    f"Value above maximum: {value} > {tag.valid_range_max}"
                )
                validation_score -= 0.3

        # Rate of change validation (if historical data available)
        # This would require querying historical data

        validation_score = max(0.0, validation_score)

        quality_metrics = {
            "range_valid": len(
                [v for v in violations if "minimum" not in v and "maximum" not in v]
            )
            == 0,
            "value": value,
            "timestamp": timestamp.isoformat(),
        }

        return ValidationResult(
            sensor_id=sensor_id,
            timestamp=timestamp,
            value=value,
            is_valid=validation_score >= 0.7,
            validation_score=validation_score,
            violations=violations,
            quality_metrics=quality_metrics,
        )

    def calculate_quality_score(self, sensor_id: str, db: Session) -> DataQualityScore:
        """Calculate comprehensive data quality score"""
        # Get recent data
        recent_data = (
            db.query(SensorData)
            .filter(
                SensorData.tag_id == sensor_id,
                SensorData.timestamp >= datetime.utcnow() - timedelta(hours=24),
            )
            .order_by(SensorData.timestamp.desc())
            .limit(1000)
            .all()
        )

        if not recent_data:
            return DataQualityScore(
                sensor_id=sensor_id,
                quality_score=0.0,
                completeness=0.0,
                accuracy=0.0,
                timeliness=0.0,
                consistency=0.0,
                validity=0.0,
                timestamp=datetime.utcnow(),
            )

        values = [d.value for d in recent_data]
        data_qualities = [d.data_quality for d in recent_data]

        # Completeness (no missing data)
        completeness = 1.0  # Assuming all data is present

        # Accuracy (based on data quality flags)
        good_count = sum(1 for q in data_qualities if q == "good")
        accuracy = good_count / len(data_qualities) if data_qualities else 0.0

        # Timeliness (data freshness)
        latest_timestamp = recent_data[0].timestamp
        time_diff = (datetime.utcnow() - latest_timestamp).total_seconds()
        timeliness = max(0.0, 1.0 - (time_diff / 3600))  # Decay over 1 hour

        # Consistency (low variance)
        if len(values) > 1:
            variance = np.var(values)
            mean_val = np.mean(values)
            consistency = 1.0 / (1.0 + variance / (mean_val**2 + 1e-6))
        else:
            consistency = 1.0

        # Validity (within expected ranges)
        valid_count = sum(1 for d in recent_data if d.data_quality != "bad")
        validity = valid_count / len(recent_data) if recent_data else 0.0

        # Overall quality score (weighted average)
        quality_score = (
            completeness * 0.2
            + accuracy * 0.3
            + timeliness * 0.2
            + consistency * 0.15
            + validity * 0.15
        )

        return DataQualityScore(
            sensor_id=sensor_id,
            quality_score=quality_score,
            completeness=completeness,
            accuracy=accuracy,
            timeliness=timeliness,
            consistency=consistency,
            validity=validity,
            timestamp=datetime.utcnow(),
        )


# Global instances
data_validator = DataValidator()


@app.post("/validate", response_model=ValidationResult)
async def validate_data_point(
    sensor_id: str,
    value: float,
    timestamp: datetime,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Validate a single data point"""
    tag = db.query(Tag).filter(Tag.tag_id == sensor_id).first()
    result = data_validator.validate(sensor_id, value, timestamp, tag)
    return result


@app.post("/validate/batch", response_model=List[ValidationResult])
async def validate_batch(
    data_points: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Validate multiple data points"""
    results = []
    for point in data_points:
        tag = db.query(Tag).filter(Tag.tag_id == point["sensor_id"]).first()
        result = data_validator.validate(
            point["sensor_id"],
            point["value"],
            datetime.fromisoformat(point["timestamp"]),
            tag,
        )
        results.append(result)
    return results


@app.post("/outliers/detect", response_model=List[OutlierResult])
async def detect_outliers(
    request: OutlierDetectionRequest,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Detect outliers in sensor data"""
    # Get recent data
    recent_data = (
        tsdb.query(SensorData)
        .filter(SensorData.tag_id == request.sensor_id)
        .order_by(SensorData.timestamp.desc())
        .limit(request.window_size)
        .all()
    )

    if len(recent_data) < 3:
        return []

    values = [d.value for d in recent_data]

    # Detect outliers
    if request.method == "zscore":
        is_outlier = StatisticalOutlierDetector.detect_zscore(values)
    elif request.method == "iqr":
        is_outlier = StatisticalOutlierDetector.detect_iqr(values)
    else:
        is_outlier = [False] * len(values)

    results = []
    for i, (data, outlier_flag) in enumerate(zip(recent_data, is_outlier)):
        if outlier_flag:
            # Calculate outlier score
            mean = np.mean(values)
            std = np.std(values)
            outlier_score = abs((data.value - mean) / std) if std > 0 else 0

            results.append(
                OutlierResult(
                    sensor_id=request.sensor_id,
                    timestamp=data.timestamp,
                    value=data.value,
                    is_outlier=True,
                    outlier_score=outlier_score,
                    method=request.method,
                )
            )

    return results


@app.post("/reconcile", response_model=List[ReconciliationResult])
async def reconcile_data(
    request: ReconciliationRequest,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Reconcile data for multiple sensors"""
    results = []

    for sensor_id in request.sensor_ids:
        # Get data in time range
        data = (
            tsdb.query(SensorData)
            .filter(
                SensorData.tag_id == sensor_id,
                SensorData.timestamp >= request.start_time,
                SensorData.timestamp <= request.end_time,
            )
            .order_by(SensorData.timestamp)
            .all()
        )

        if not data:
            continue

        values = [d.value for d in data]
        timestamps = [d.timestamp for d in data]

        # Reconcile
        if request.reconciliation_method == "statistical":
            reconciled_values = DataReconciler.reconcile_statistical(values, timestamps)
        elif request.reconciliation_method == "interpolation":
            reconciled_values = DataReconciler.reconcile_interpolation(
                values, timestamps, []
            )
        else:
            reconciled_values = values

        # Create results
        for i, (original, reconciled) in enumerate(zip(values, reconciled_values)):
            if abs(original - reconciled) > 0.01:  # Only if significant difference
                results.append(
                    ReconciliationResult(
                        sensor_id=sensor_id,
                        original_value=original,
                        reconciled_value=reconciled,
                        reconciliation_method=request.reconciliation_method,
                        confidence=0.85,
                        timestamp=timestamps[i],
                    )
                )

    return results


@app.get("/quality/{sensor_id}", response_model=DataQualityScore)
async def get_quality_score(
    sensor_id: str,
    db: Session = Depends(get_db),
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get data quality score for a sensor"""
    return data_validator.calculate_quality_score(sensor_id, tsdb)


@app.get("/quality", response_model=List[DataQualityScore])
async def get_all_quality_scores(
    db: Session = Depends(get_db),
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get quality scores for all sensors"""
    tags = db.query(Tag).filter(Tag.status == "active").all()
    scores = []
    for tag in tags:
        score = data_validator.calculate_quality_score(tag.tag_id, tsdb)
        scores.append(score)
    return scores


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "dvr",
        "validation_rules": len(data_validator.validation_rules),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8011)
