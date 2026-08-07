"""
Secure Command Workflow with 2FA and Digital Twin Simulation
Two-stage secure command workflow combining 2FA with Digital Twin validation.

State is persisted on the `commands` row (not an in-memory dict) so it
survives process restarts and is shared across worker processes/replicas.
"""
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from enum import Enum

import httpx
from sqlalchemy.orm import Session

from .config import settings
from .models import Command, User
from .security import verify_2fa_token
from .kafka_utils import KafkaProducerWrapper, KAFKA_TOPICS, create_low_latency_producer

logger = logging.getLogger(__name__)


class CommandStage(Enum):
    """Command workflow stages"""

    REQUESTED = "requested"
    TWO_FA_VERIFIED = "two_fa_verified"
    DIGITAL_TWIN_SIMULATION = "digital_twin_simulation"
    SIMULATION_APPROVED = "simulation_approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


class SecureCommandWorkflow:
    """
    Secure multi-stage command workflow, backed by the `commands` table:
    1. Two-Factor Authentication (2FA)
    2. Digital Twin Simulation
    3. Human approval (two-person rule)
    4. Execution (published to Kafka for SCADA/PLC pickup)
    """

    def __init__(self):
        self.digital_twin_service_url = settings.DIGITAL_TWIN_SERVICE_URL
        self._command_producer: Optional[KafkaProducerWrapper] = None
        self._critical_command_producer: Optional[KafkaProducerWrapper] = None

    def init_producers(self) -> None:
        """Create Kafka producers. Call once at service startup."""
        self._command_producer = KafkaProducerWrapper(KAFKA_TOPICS["CONTROL_COMMANDS"])
        self._critical_command_producer = create_low_latency_producer(
            KAFKA_TOPICS["CRITICAL_CONTROL_COMMANDS"]
        )

    def close_producers(self) -> None:
        if self._command_producer:
            self._command_producer.close()
        if self._critical_command_producer:
            self._critical_command_producer.close()

    def _get_command(self, db: Session, command_id: str) -> Command:
        command = db.query(Command).filter(Command.command_id == command_id).first()
        if not command:
            raise ValueError(f"Command {command_id} not found")
        return command

    async def initiate_command(
        self,
        db: Session,
        command_id: str,
        command_type: str,
        parameters: Dict[str, Any],
        requested_by_id: int,
        well_name: str,
        equipment_id: str,
        critical: bool = False,
    ) -> Dict[str, Any]:
        """Stage 1: create the command, awaiting 2FA."""
        command = Command(
            command_id=command_id,
            timestamp=datetime.utcnow(),
            well_name=well_name,
            equipment_id=equipment_id,
            command_type=command_type,
            parameters=parameters,
            status="pending",
            stage=CommandStage.REQUESTED.value,
            requested_by_id=requested_by_id,
            requires_two_factor=True,
            critical=critical,
        )
        db.add(command)
        db.commit()

        logger.info(f"Command {command_id} initiated, awaiting 2FA")

        return {
            "command_id": command_id,
            "stage": CommandStage.REQUESTED.value,
            "next_step": "two_factor_authentication",
            "message": "Command requested. Two-factor authentication required.",
        }

    async def verify_two_factor(
        self,
        db: Session,
        command_id: str,
        two_fa_code: str,
        user: User,
    ) -> Dict[str, Any]:
        """Stage 2: verify the requester's real TOTP 2FA code."""
        command = self._get_command(db, command_id)

        if command.stage != CommandStage.REQUESTED.value:
            return {"error": f"Command is not awaiting 2FA (stage={command.stage})"}

        if not user.two_factor_enabled or not user.two_factor_secret:
            return {"error": "2FA is not enabled for this user; cannot verify command"}

        if not verify_2fa_token(user.two_factor_secret, two_fa_code):
            command.stage = CommandStage.REJECTED.value
            command.status = "rejected"
            db.commit()
            return {
                "command_id": command_id,
                "stage": CommandStage.REJECTED.value,
                "error": "Invalid 2FA code",
            }

        command.stage = CommandStage.TWO_FA_VERIFIED.value
        command.two_fa_verified_at = datetime.utcnow()
        db.commit()

        logger.info(
            f"Command {command_id} - 2FA verified, proceeding to Digital Twin simulation"
        )

        return await self.run_digital_twin_simulation(db, command_id)

    async def run_digital_twin_simulation(
        self, db: Session, command_id: str
    ) -> Dict[str, Any]:
        """Stage 3: run Digital Twin simulation before execution."""
        command = self._get_command(db, command_id)

        if command.stage != CommandStage.TWO_FA_VERIFIED.value:
            return {"error": "2FA verification required before simulation"}

        try:
            async with httpx.AsyncClient() as client:
                simulation_request = {
                    "well_name": command.well_name,
                    "parameters": {
                        **(command.parameters or {}),
                        "command_type": command.command_type,
                        "equipment_id": command.equipment_id,
                    },
                    "simulation_type": f"command_simulation_{command.command_type}",
                }

                response = await client.post(
                    f"{self.digital_twin_service_url}/simulate",
                    json=simulation_request,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise RuntimeError(f"Simulation failed: {response.status_code}")

                simulation_result = response.json()
                command.stage = CommandStage.DIGITAL_TWIN_SIMULATION.value
                command.simulation_result = simulation_result
                db.commit()

                logger.info(f"Command {command_id} - Digital Twin simulation completed")

                return {
                    "command_id": command_id,
                    "stage": CommandStage.DIGITAL_TWIN_SIMULATION.value,
                    "simulation_result": simulation_result,
                    "next_step": "review_simulation",
                    "message": "Digital Twin simulation completed. Review results before approval.",
                }

        except Exception as e:
            logger.error(f"Digital Twin simulation error for command {command_id}: {e}")
            command.stage = CommandStage.REJECTED.value
            command.status = "rejected"
            db.commit()
            return {
                "command_id": command_id,
                "stage": CommandStage.REJECTED.value,
                "error": f"Simulation failed: {str(e)}",
            }

    async def approve_simulation(
        self,
        db: Session,
        command_id: str,
        approver: User,
        approval_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage 4: approve simulation results. Enforces the two-person rule."""
        command = self._get_command(db, command_id)

        if command.stage != CommandStage.DIGITAL_TWIN_SIMULATION.value:
            return {"error": "Digital Twin simulation must be completed first"}

        if command.requested_by_id == approver.id:
            return {"error": "Cannot approve own command (two-person rule)"}

        simulation_result = command.simulation_result or {}
        results = simulation_result.get("results", {})

        # Safety check (example threshold - tune per well/equipment profile)
        if results.get("predicted_pressure", 0) > 500:
            command.stage = CommandStage.REJECTED.value
            command.status = "rejected"
            db.commit()
            return {
                "error": "Simulation predicts unsafe conditions. Command rejected.",
                "simulation_result": simulation_result,
            }

        command.stage = CommandStage.SIMULATION_APPROVED.value
        command.status = "approved"
        command.approved_by_id = approver.id
        command.approval_notes = approval_notes
        db.commit()

        logger.info(
            f"Command {command_id} - Simulation approved by {approver.username}"
        )

        return {
            "command_id": command_id,
            "stage": CommandStage.SIMULATION_APPROVED.value,
            "next_step": "execute",
            "message": "Simulation approved. Command ready for execution.",
            "simulation_result": simulation_result,
        }

    def _publish(self, command: Command) -> None:
        """Publish a command to Kafka for SCADA/PLC pickup. Raises on failure."""
        command_data = {
            "command_id": command.command_id,
            "well_name": command.well_name,
            "equipment_id": command.equipment_id,
            "command_type": command.command_type,
            "parameters": command.parameters,
        }

        if command.critical and self._critical_command_producer:
            self._critical_command_producer.send(
                command.command_id, command_data, flush_immediately=False
            )
        elif self._command_producer:
            self._command_producer.send(command.command_id, command_data)
            self._command_producer.flush()
        else:
            raise RuntimeError("No Kafka producer available")

    async def execute_command(
        self, db: Session, command_id: str, executor: User
    ) -> Dict[str, Any]:
        """Stage 5: execute the command by publishing it to Kafka for SCADA/PLC pickup."""
        command = self._get_command(db, command_id)

        if command.stage != CommandStage.SIMULATION_APPROVED.value:
            return {
                "error": "Command must be 2FA-verified, simulated, and approved before execution"
            }

        command.status = "executing"
        db.commit()

        try:
            self._publish(command)
        except Exception as e:
            logger.error(f"Failed to publish command {command_id} to Kafka: {e}")
            command.stage = CommandStage.FAILED.value
            command.status = "failed"
            db.commit()
            return {
                "command_id": command_id,
                "stage": CommandStage.FAILED.value,
                "error": "Failed to execute command",
            }

        command.stage = CommandStage.EXECUTED.value
        command.status = "executed"
        command.executed_at = datetime.utcnow()
        command.execution_result = {
            "status": "success",
            "message": "Command sent to SCADA",
            "executed_by": executor.username,
        }
        db.commit()

        logger.info(
            f"Command {command_id} - Executed successfully by {executor.username}"
        )

        return {
            "command_id": command_id,
            "stage": CommandStage.EXECUTED.value,
            "message": "Command executed successfully",
            "execution_timestamp": command.executed_at.isoformat(),
        }

    async def execute_immediately(
        self, db: Session, command: Command, executor: User
    ) -> Dict[str, Any]:
        """
        Bypass the 2FA/simulation/approval gates and publish straight to Kafka.

        For emergency-stop style actions only, where requiring 2FA or a second
        approver would defeat the purpose of an immediate safety action.
        """
        command.status = "executing"
        db.commit()

        try:
            self._publish(command)
        except Exception as e:
            logger.error(
                f"Failed to publish emergency command {command.command_id} to Kafka: {e}"
            )
            command.stage = CommandStage.FAILED.value
            command.status = "failed"
            db.commit()
            return {
                "command_id": command.command_id,
                "stage": CommandStage.FAILED.value,
                "error": "Failed to execute command",
            }

        command.stage = CommandStage.EXECUTED.value
        command.status = "executed"
        command.executed_at = datetime.utcnow()
        command.execution_result = {
            "status": "success",
            "message": "Command sent to SCADA",
            "executed_by": executor.username,
        }
        db.commit()

        logger.critical(
            f"Command {command.command_id} - Executed immediately by {executor.username} (no approval gate)"
        )

        return {
            "command_id": command.command_id,
            "stage": CommandStage.EXECUTED.value,
            "message": "Command executed successfully",
            "execution_timestamp": command.executed_at.isoformat(),
        }

    def get_command_status(
        self, db: Session, command_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get current status of a command"""
        command = db.query(Command).filter(Command.command_id == command_id).first()
        if not command:
            return None

        return {
            "command_id": command.command_id,
            "stage": command.stage,
            "status": command.status,
            "simulation_result": command.simulation_result,
        }


# Global instance. Call init_producers()/close_producers() from each
# service's startup/shutdown events before using execute_command().
secure_command_workflow = SecureCommandWorkflow()
