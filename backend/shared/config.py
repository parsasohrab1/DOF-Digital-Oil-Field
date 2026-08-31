"""
Shared configuration management
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
DEFAULT_ENV_FILE = ROOT_DIR / ".env"

_env_file_override = os.getenv("OGIM_ENV_FILE")
env_name = os.getenv("ENVIRONMENT", "development").lower()
search_candidates = []
if _env_file_override:
    candidate_env_file = Path(_env_file_override)
    if not candidate_env_file.is_absolute():
        candidate_env_file = ROOT_DIR / candidate_env_file
    search_candidates.append(candidate_env_file)
else:
    search_candidates.extend(
        [
            CONFIG_DIR / f".env.{env_name}",
            CONFIG_DIR / f"{env_name}.env",
        ]
    )

candidate_env_file = None
for candidate in search_candidates:
    if candidate.exists():
        candidate_env_file = candidate
        break
    example_candidate = candidate.with_name(candidate.name + ".example")
    if example_candidate.exists():
        candidate_env_file = example_candidate
        break

if candidate_env_file is None:
    candidate_env_file = DEFAULT_ENV_FILE
elif candidate_env_file.name.endswith(".example") and env_name == "production":
    # Never silently boot production off a placeholder example env file.
    raise RuntimeError(
        f"No real env file found for ENVIRONMENT=production; refusing to fall back to "
        f"placeholder file '{candidate_env_file}'. Create the real env file instead."
    )

DEFAULT_SECRET_KEY = "change-this-secret-key-in-production-minimum-32-characters"
DEFAULT_DB_PASSWORD = "ogim_password"


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "OGIM"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://ogim_user:ogim_password@postgres:5432/ogim",
        env="DATABASE_URL",
    )
    DATABASE_POOL_SIZE: int = Field(default=20, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=40, env="DATABASE_MAX_OVERFLOW")
    DATABASE_POOL_RECYCLE_SECONDS: int = Field(
        default=1800, env="DATABASE_POOL_RECYCLE_SECONDS"
    )
    DATABASE_POOL_TIMEOUT_SECONDS: int = Field(
        default=30, env="DATABASE_POOL_TIMEOUT_SECONDS"
    )
    TIMESCALE_URL: str = Field(
        default="postgresql://ogim_user:ogim_password@timescaledb:5432/ogim_tsdb",
        env="TIMESCALE_URL",
    )

    # TimescaleDB Multi-node Settings
    TIMESCALE_MULTI_NODE_ENABLED: bool = Field(
        default=False, env="TIMESCALE_MULTI_NODE_ENABLED"
    )
    TIMESCALE_ACCESS_NODES: Optional[str] = Field(
        default=None,
        env="TIMESCALE_ACCESS_NODES",  # Comma-separated: node1:5432,node2:5432
    )
    TIMESCALE_DATA_NODES: Optional[str] = Field(
        default=None,
        env="TIMESCALE_DATA_NODES",  # Comma-separated: node1:5432,node2:5432,node3:5432
    )
    TIMESCALE_CONNECTION_POOL_SIZE: int = Field(
        default=20, env="TIMESCALE_CONNECTION_POOL_SIZE"
    )
    TIMESCALE_MAX_OVERFLOW: int = Field(default=40, env="TIMESCALE_MAX_OVERFLOW")
    TIMESCALE_CHUNK_TIME_INTERVAL: str = Field(
        default="1 day",  # Chunk interval for hypertables
        env="TIMESCALE_CHUNK_TIME_INTERVAL",
    )
    TIMESCALE_COMPRESSION_AFTER_DAYS: int = Field(
        default=90,  # Compress chunks older than 90 days
        env="TIMESCALE_COMPRESSION_AFTER_DAYS",
    )
    TIMESCALE_RETENTION_DAYS: int = Field(
        default=365, env="TIMESCALE_RETENTION_DAYS"  # Retain data for 365 days
    )
    TIMESCALE_NUMBER_PARTITIONS: int = Field(
        default=4,  # Number of partitions for distributed hypertables
        env="TIMESCALE_NUMBER_PARTITIONS",
    )

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka:9092", env="KAFKA_BOOTSTRAP_SERVERS"
    )
    KAFKA_SCHEMA_REGISTRY_URL: str = Field(
        default="http://schema-registry:8081", env="KAFKA_SCHEMA_REGISTRY_URL"
    )

    # Kafka Low-Latency Settings (for critical controls)
    KAFKA_LOW_LATENCY_MODE: bool = Field(default=False, env="KAFKA_LOW_LATENCY_MODE")
    KAFKA_PRODUCER_ACKS: str = Field(
        default="all",  # "0", "1", or "all" - use "1" or "0" for low-latency
        env="KAFKA_PRODUCER_ACKS",
    )
    KAFKA_PRODUCER_LINGER_MS: int = Field(
        default=0,  # 0 for immediate send, higher for batching
        env="KAFKA_PRODUCER_LINGER_MS",
    )
    KAFKA_PRODUCER_BATCH_SIZE: int = Field(
        default=16384,  # bytes - use 1 for critical controls
        env="KAFKA_PRODUCER_BATCH_SIZE",
    )
    KAFKA_PRODUCER_COMPRESSION_TYPE: str = Field(
        default="none",  # "none", "gzip", "snappy", "lz4" - "none" for lowest latency
        env="KAFKA_PRODUCER_COMPRESSION_TYPE",
    )
    KAFKA_CONSUMER_FETCH_MIN_BYTES: int = Field(
        default=1,  # Minimum bytes to fetch - 1 for lowest latency
        env="KAFKA_CONSUMER_FETCH_MIN_BYTES",
    )
    KAFKA_CONSUMER_FETCH_MAX_WAIT_MS: int = Field(
        default=0,  # Max wait time - 0 for immediate fetch
        env="KAFKA_CONSUMER_FETCH_MAX_WAIT_MS",
    )

    # Redis (for caching and session)
    REDIS_URL: str = Field(default="redis://redis:6379/0", env="REDIS_URL")

    # Security
    SECRET_KEY: str = Field(
        default="change-this-secret-key-in-production-minimum-32-characters",
        env="SECRET_KEY",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: list = Field(
        default=["http://localhost:3000", "http://localhost:5173"], env="CORS_ORIGINS"
    )

    # Services URLs (for API Gateway)
    AUTH_SERVICE_URL: str = Field(
        default="http://auth-service:8001", env="AUTH_SERVICE_URL"
    )
    DATA_INGESTION_SERVICE_URL: str = Field(
        default="http://data-ingestion-service:8002", env="DATA_INGESTION_SERVICE_URL"
    )
    ML_INFERENCE_SERVICE_URL: str = Field(
        default="http://ml-inference-service:8003", env="ML_INFERENCE_SERVICE_URL"
    )
    ALERT_SERVICE_URL: str = Field(
        default="http://alert-service:8004", env="ALERT_SERVICE_URL"
    )
    REPORTING_SERVICE_URL: str = Field(
        default="http://reporting-service:8005", env="REPORTING_SERVICE_URL"
    )
    COMMAND_CONTROL_SERVICE_URL: str = Field(
        default="http://command-control-service:8006", env="COMMAND_CONTROL_SERVICE_URL"
    )
    TAG_CATALOG_SERVICE_URL: str = Field(
        default="http://tag-catalog-service:8007", env="TAG_CATALOG_SERVICE_URL"
    )
    DIGITAL_TWIN_SERVICE_URL: str = Field(
        default="http://digital-twin-service:8008", env="DIGITAL_TWIN_SERVICE_URL"
    )
    DVR_SERVICE_URL: str = Field(
        default="http://dvr-service:8011", env="DVR_SERVICE_URL"
    )
    REMOTE_OPERATIONS_SERVICE_URL: str = Field(
        default="http://remote-operations-service:8012",
        env="REMOTE_OPERATIONS_SERVICE_URL",
    )
    DATA_VARIABLES_SERVICE_URL: str = Field(
        default="http://data-variables-service:8013", env="DATA_VARIABLES_SERVICE_URL"
    )
    STORAGE_OPTIMIZATION_SERVICE_URL: str = Field(
        default="http://storage-optimization-service:8014",
        env="STORAGE_OPTIMIZATION_SERVICE_URL",
    )

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REDIS_URL: Optional[str] = Field(
        default=None, env="RATE_LIMIT_REDIS_URL"
    )
    RATE_LIMIT_STRATEGY: str = Field(
        default="sliding_window", env="RATE_LIMIT_STRATEGY"
    )  # sliding_window or token_bucket

    # mTLS Configuration
    MTLS_ENABLED: bool = Field(default=False, env="MTLS_ENABLED")
    MTLS_CERT_DIR: Optional[str] = Field(default=None, env="MTLS_CERT_DIR")
    MTLS_CA_CERT_PATH: Optional[str] = Field(default=None, env="MTLS_CA_CERT_PATH")
    MTLS_CLIENT_CERT_PATH: Optional[str] = Field(
        default=None, env="MTLS_CLIENT_CERT_PATH"
    )
    MTLS_CLIENT_KEY_PATH: Optional[str] = Field(
        default=None, env="MTLS_CLIENT_KEY_PATH"
    )
    MTLS_VERIFY_SERVER: bool = Field(default=True, env="MTLS_VERIFY_SERVER")

    # MQTT Configuration
    MQTT_ENABLED: bool = Field(default=False, env="MQTT_ENABLED")
    MQTT_BROKER_HOST: str = Field(default="localhost", env="MQTT_BROKER_HOST")
    MQTT_BROKER_PORT: int = Field(default=1883, env="MQTT_BROKER_PORT")
    MQTT_USERNAME: Optional[str] = Field(default=None, env="MQTT_USERNAME")
    MQTT_PASSWORD: Optional[str] = Field(default=None, env="MQTT_PASSWORD")
    MQTT_QOS: int = Field(default=1, env="MQTT_QOS")  # 0, 1, or 2
    MQTT_TOPICS: str = Field(
        default="sensors/+/data,sensors/+/status", env="MQTT_TOPICS"
    )  # Comma-separated

    # LoRaWAN Configuration
    LORAWAN_ENABLED: bool = Field(default=False, env="LORAWAN_ENABLED")
    LORAWAN_NETWORK_TYPE: str = Field(
        default="ttn", env="LORAWAN_NETWORK_TYPE"
    )  # "ttn" or "chirpstack"
    LORAWAN_API_URL: Optional[str] = Field(default=None, env="LORAWAN_API_URL")
    LORAWAN_API_KEY: Optional[str] = Field(default=None, env="LORAWAN_API_KEY")
    LORAWAN_APP_ID: Optional[str] = Field(default=None, env="LORAWAN_APP_ID")
    LORAWAN_WEBHOOK_URL: Optional[str] = Field(default=None, env="LORAWAN_WEBHOOK_URL")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = "json"  # json or text

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(
        default="http://localhost:4317",
        env="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    OTEL_TRACING_CONSOLE: bool = Field(default=False, env="OTEL_TRACING_CONSOLE")

    # Zero Trust / SIEM / Threat Detection
    ZERO_TRUST_ENFORCED: bool = Field(default=True, env="ZERO_TRUST_ENFORCED")
    ZERO_TRUST_ALLOWED_NETWORKS: Optional[str] = Field(
        default="127.0.0.1/32,10.0.0.0/8,192.168.0.0/16",
        env="ZERO_TRUST_ALLOWED_NETWORKS",
    )
    THREAT_BLOCK_THRESHOLD: int = Field(default=70, env="THREAT_BLOCK_THRESHOLD")
    SIEM_OUTPUT_FILE: Optional[str] = Field(default=None, env="SIEM_OUTPUT_FILE")

    # API / Cache performance tuning
    API_GATEWAY_UPSTREAM_TIMEOUT_SECONDS: int = Field(
        default=15, env="API_GATEWAY_UPSTREAM_TIMEOUT_SECONDS"
    )
    API_GATEWAY_HTTP_KEEPALIVE_CONNECTIONS: int = Field(
        default=100, env="API_GATEWAY_HTTP_KEEPALIVE_CONNECTIONS"
    )
    API_GATEWAY_HTTP_MAX_CONNECTIONS: int = Field(
        default=300, env="API_GATEWAY_HTTP_MAX_CONNECTIONS"
    )

    # Shared secret for service-to-service pushes into the Gateway's realtime
    # WebSocket stream (see POST /internal/realtime/publish). Not a user-facing
    # credential -- change it per environment via env var like any other secret.
    INTERNAL_SERVICE_TOKEN: str = Field(
        default="dev-internal-token-change-in-production", env="INTERNAL_SERVICE_TOKEN"
    )
    API_SECURITY_MAX_BODY_BYTES: int = Field(
        default=1024 * 1024, env="API_SECURITY_MAX_BODY_BYTES"
    )
    API_SECURITY_MAX_QUERY_PARAMS: int = Field(
        default=50, env="API_SECURITY_MAX_QUERY_PARAMS"
    )
    API_SECURITY_MAX_PARAM_LENGTH: int = Field(
        default=1024, env="API_SECURITY_MAX_PARAM_LENGTH"
    )
    API_SECURITY_ENABLE_INPUT_HARDENING: bool = Field(
        default=True, env="API_SECURITY_ENABLE_INPUT_HARDENING"
    )
    CACHE_TTL_SECONDS: int = Field(default=30, env="CACHE_TTL_SECONDS")
    CACHE_MAX_ENTRIES: int = Field(default=2048, env="CACHE_MAX_ENTRIES")

    # OPC-UA / SCADA
    OPCUA_SERVER_URL: Optional[str] = Field(default=None, env="OPCUA_SERVER_URL")
    OPCUA_USERNAME: Optional[str] = Field(default=None, env="OPCUA_USERNAME")
    OPCUA_PASSWORD: Optional[str] = Field(default=None, env="OPCUA_PASSWORD")

    # ML Models
    MODEL_STORAGE_PATH: str = Field(default="/app/models", env="MODEL_STORAGE_PATH")
    MLFLOW_TRACKING_URI: Optional[str] = Field(default=None, env="MLFLOW_TRACKING_URI")

    # Offline Buffer Settings
    OFFLINE_BUFFER_ENABLED: bool = Field(default=True, env="OFFLINE_BUFFER_ENABLED")
    OFFLINE_BUFFER_PATH: str = Field(default="./data/buffer", env="OFFLINE_BUFFER_PATH")
    OFFLINE_BUFFER_MAX_SIZE: int = Field(
        default=100000, env="OFFLINE_BUFFER_MAX_SIZE"
    )  # Max records
    OFFLINE_BUFFER_MAX_SIZE_MB: int = Field(
        default=500, env="OFFLINE_BUFFER_MAX_SIZE_MB"
    )  # Max size in MB
    OFFLINE_BUFFER_CLEANUP_INTERVAL: int = Field(
        default=3600, env="OFFLINE_BUFFER_CLEANUP_INTERVAL"
    )  # seconds

    # Connection Monitor Settings
    CONNECTION_MONITOR_ENABLED: bool = Field(
        default=True, env="CONNECTION_MONITOR_ENABLED"
    )
    CONNECTION_CHECK_INTERVAL: int = Field(
        default=5, env="CONNECTION_CHECK_INTERVAL"
    )  # seconds
    CONNECTION_CHECK_TIMEOUT: int = Field(
        default=3, env="CONNECTION_CHECK_TIMEOUT"
    )  # seconds
    CONNECTION_CHECK_HOSTS: Optional[str] = Field(
        default=None, env="CONNECTION_CHECK_HOSTS"
    )  # comma-separated host:port
    CONNECTION_CHECK_URLS: Optional[str] = Field(
        default=None, env="CONNECTION_CHECK_URLS"
    )  # comma-separated URLs

    # Retry Settings
    RETRY_MAX_ATTEMPTS: int = Field(default=10, env="RETRY_MAX_ATTEMPTS")
    RETRY_BACKOFF_FACTOR: float = Field(default=2.0, env="RETRY_BACKOFF_FACTOR")
    RETRY_INITIAL_DELAY: int = Field(default=1, env="RETRY_INITIAL_DELAY")  # seconds

    # Edge Computing Settings
    EDGE_COMPUTING_ENABLED: bool = Field(default=False, env="EDGE_COMPUTING_ENABLED")
    EDGE_SERVICE_URL: str = Field(
        default="http://edge-computing-service:8009", env="EDGE_SERVICE_URL"
    )

    # Industrial Security Settings
    INDUSTRIAL_SECURITY_ENABLED: bool = Field(
        default=True, env="INDUSTRIAL_SECURITY_ENABLED"
    )
    MODBUS_SECURITY_ENABLED: bool = Field(default=True, env="MODBUS_SECURITY_ENABLED")
    LAYER1_SECURITY_ENABLED: bool = Field(default=True, env="LAYER1_SECURITY_ENABLED")
    LAYER2_SECURITY_ENABLED: bool = Field(default=True, env="LAYER2_SECURITY_ENABLED")

    # Connectivity Settings (5G/Satellite)
    CONNECTIVITY_MANAGER_ENABLED: bool = Field(
        default=False, env="CONNECTIVITY_MANAGER_ENABLED"
    )
    CONNECTION_PRIORITY: Optional[str] = Field(
        default=None,
        env="CONNECTION_PRIORITY",  # Comma-separated: ethernet,5g,4g,satellite
    )

    # ERP Integration Settings
    ERP_INTEGRATION_ENABLED: bool = Field(default=False, env="ERP_INTEGRATION_ENABLED")
    ERP_SERVICE_URL: str = Field(
        default="http://erp-integration-service:8010", env="ERP_SERVICE_URL"
    )
    ERP_DEFAULT_SYSTEM: str = Field(
        default="sap", env="ERP_DEFAULT_SYSTEM"
    )  # sap, oracle, maximo
    ERP_AUTO_CREATE_WORK_ORDERS: bool = Field(
        default=False, env="ERP_AUTO_CREATE_WORK_ORDERS"
    )

    # SMS Alert Notifications (Kavenegar / Twilio / mock)
    SMS_ENABLED: bool = Field(default=True, env="SMS_ENABLED")
    SMS_PROVIDER: str = Field(
        default="mock", env="SMS_PROVIDER"
    )  # mock|kavenegar|twilio
    SMS_SEVERITIES: str = Field(default="critical,warning", env="SMS_SEVERITIES")
    KAVENEGAR_API_KEY: Optional[str] = Field(default=None, env="KAVENEGAR_API_KEY")
    KAVENEGAR_SENDER: str = Field(default="10008663", env="KAVENEGAR_SENDER")
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    TWILIO_FROM_NUMBER: Optional[str] = Field(default=None, env="TWILIO_FROM_NUMBER")

    class Config:
        env_file = candidate_env_file
        case_sensitive = True

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> "Settings":
        """Fail fast rather than silently booting production with forgeable secrets."""
        if self.ENVIRONMENT.lower() != "production":
            return self

        problems = []
        if self.SECRET_KEY == DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < 32:
            problems.append(
                "SECRET_KEY is missing/default/too short (need a real value >= 32 chars)"
            )
        if DEFAULT_DB_PASSWORD in self.DATABASE_URL:
            problems.append(
                "DATABASE_URL still contains the default placeholder password"
            )
        if DEFAULT_DB_PASSWORD in self.TIMESCALE_URL:
            problems.append(
                "TIMESCALE_URL still contains the default placeholder password"
            )

        if problems:
            raise ValueError(
                "Refusing to start with ENVIRONMENT=production and placeholder secrets: "
                + "; ".join(problems)
            )
        return self


# Global settings instance
settings = Settings()
