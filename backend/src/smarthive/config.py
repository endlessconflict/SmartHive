from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables with the SMARTHIVE_ prefix; a local .env file is read too."""

    model_config = SettingsConfigDict(env_prefix="SMARTHIVE_", env_file=".env", extra="ignore")

    db_url: str = "postgresql+asyncpg://smarthive:smarthive@localhost:5432/smarthive"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls_ca: str | None = None  # path to the CA certificate; when set, TLS is used
    # The broker in infra/ requires a client certificate and takes the MQTT user from its CN (`backend`)
    mqtt_tls_cert: str | None = None
    mqtt_tls_key: str | None = None
    mqtt_client_id: str = "smarthive-ingest"
    log_level: str = "INFO"
