"""
Federated Learning coordinator: privacy-preserving distributed training.

Edge nodes train a small local model on their own sensor data and submit
ONLY the resulting model weights (never raw data) to this coordinator,
which aggregates them via FedAvg (a data-size-weighted average, McMahan et
al. 2017) into a global model.

This replaces a frontend-only mock (hardcoded node list, Math.random()
"training history") with real, testable aggregation math and a genuine
local-training helper an edge node can call before submitting.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Fixed feature order local models are trained/averaged on, so weight vectors
# from different nodes are directly comparable -- FedAvg requires every
# participant's model to have the same shape.
FEATURE_NAMES = ["pressure", "temperature", "flow_rate", "vibration"]
WEIGHT_DIM = len(FEATURE_NAMES) + 1  # + bias term

CONVERGENCE_ACCURACY_DELTA = 0.001  # 0.1 percentage points
CONVERGENCE_WINDOW = 3


@dataclass
class EdgeNodeState:
    node_id: str
    well_name: str
    location: str
    local_weights: List[float]
    local_accuracy: float
    data_size: int
    status: str = "syncing"  # idle | training | syncing
    last_sync: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class FederatedLearningCoordinator:
    """In-memory FedAvg coordinator (mirrors the existing in-memory state
    pattern already used for A/B test config and drift baselines in
    mlflow_integration.py -- not a database, just process state)."""

    def __init__(self) -> None:
        self.nodes: Dict[str, EdgeNodeState] = {}
        self.round_number = 0
        self.global_weights: Optional[List[float]] = None
        self.global_accuracy: Optional[float] = None
        self.round_history: List[Dict[str, Any]] = []

    def submit_local_update(
        self,
        node_id: str,
        well_name: str,
        location: str,
        local_weights: List[float],
        local_accuracy: float,
        data_size: int,
    ) -> EdgeNodeState:
        if len(local_weights) != WEIGHT_DIM:
            raise ValueError(
                f"local_weights must have length {WEIGHT_DIM} (got {len(local_weights)})."
            )
        if data_size <= 0:
            raise ValueError("data_size must be positive.")
        if not (0.0 <= local_accuracy <= 1.0):
            raise ValueError("local_accuracy must be between 0 and 1.")

        node = EdgeNodeState(
            node_id=node_id,
            well_name=well_name,
            location=location,
            local_weights=list(local_weights),
            local_accuracy=local_accuracy,
            data_size=int(data_size),
            status="syncing",
        )
        self.nodes[node_id] = node
        logger.info(
            "Federated node %s submitted a local update (data_size=%d)",
            node_id,
            data_size,
        )
        return node

    def aggregate_round(self, min_nodes: int = 2) -> Dict[str, Any]:
        """Run one FedAvg round: a data-size-weighted average of every
        currently-registered node's local_weights, producing a new global
        model. Requires at least `min_nodes` participants."""
        if len(self.nodes) < min_nodes:
            raise ValueError(
                f"Need at least {min_nodes} participating nodes to aggregate (have {len(self.nodes)})."
            )

        nodes = list(self.nodes.values())
        total_data = sum(n.data_size for n in nodes)
        weight_matrix = np.array([n.local_weights for n in nodes])
        sample_weights = np.array([n.data_size / total_data for n in nodes])

        new_global_weights = np.average(weight_matrix, axis=0, weights=sample_weights)
        new_global_accuracy = float(
            np.average([n.local_accuracy for n in nodes], weights=sample_weights)
        )

        self.round_number += 1
        self.global_weights = new_global_weights.tolist()
        previous_accuracy = self.global_accuracy
        self.global_accuracy = new_global_accuracy

        for node in nodes:
            node.status = "idle"
            node.last_sync = datetime.utcnow().isoformat()

        round_entry = {
            "round": self.round_number,
            "global_accuracy": new_global_accuracy,
            "avg_local_accuracy": float(np.mean([n.local_accuracy for n in nodes])),
            "participating_nodes": len(nodes),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.round_history.append(round_entry)

        return {
            "round": self.round_number,
            "global_weights": self.global_weights,
            "global_accuracy": self.global_accuracy,
            "accuracy_delta": (
                None
                if previous_accuracy is None
                else new_global_accuracy - previous_accuracy
            ),
            "participating_nodes": len(nodes),
            "convergence_status": self.convergence_status(),
        }

    def convergence_status(self) -> str:
        if len(self.round_history) < 2:
            return "converging"
        recent = self.round_history[-CONVERGENCE_WINDOW:]
        deltas = [
            recent[i]["global_accuracy"] - recent[i - 1]["global_accuracy"]
            for i in range(1, len(recent))
        ]
        if not deltas:
            return "converging"
        if all(d < -1e-9 for d in deltas):
            return "diverging"
        if all(abs(d) < CONVERGENCE_ACCURACY_DELTA for d in deltas):
            return "converged"
        return "converging"

    def get_state(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "well_name": n.well_name,
                    "location": n.location,
                    "local_accuracy": n.local_accuracy,
                    "data_size": n.data_size,
                    "status": n.status,
                    "last_sync": n.last_sync,
                }
                for n in self.nodes.values()
            ],
            "global_model": {
                "round": self.round_number,
                "global_accuracy": self.global_accuracy,
                "participating_nodes": len(self.nodes),
                "convergence_status": self.convergence_status(),
                "has_global_model": self.global_weights is not None,
            },
            "round_history": self.round_history,
        }


def train_local_linear_model(
    samples: List[Dict[str, float]], labels: List[float]
) -> Dict[str, Any]:
    """Fit a small local model on this node's own sensor data and return
    ONLY its coefficients. The raw `samples`/`labels` are meant to stay on
    the caller's own process/device -- only this function's return value
    (a handful of floats) is what gets submitted to the coordinator.
    """
    from sklearn.linear_model import LogisticRegression

    if len(samples) < 2:
        raise ValueError("Need at least 2 samples to fit a local model.")
    if len(set(labels)) < 2:
        raise ValueError("Need both positive and negative labels to fit a local model.")

    x = np.array([[s.get(f, 0.0) for f in FEATURE_NAMES] for s in samples])
    y = np.array(labels)

    model = LogisticRegression(max_iter=1000)
    model.fit(x, y)
    weights = model.coef_[0].tolist() + [float(model.intercept_[0])]
    accuracy = float(model.score(x, y))

    return {
        "local_weights": weights,
        "local_accuracy": accuracy,
        "data_size": len(samples),
        "feature_names": FEATURE_NAMES,
    }


federated_coordinator = FederatedLearningCoordinator()
