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

    # API. There is no default secret on purpose: `smarthive api` refuses to start without one.
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = True  # the refresh cookie is Secure; browsers still accept it on http://localhost
    login_max_failures: int = 5  # per client address, within login_window_s
    login_window_s: int = 900
    forwarded_allow_ips: str = "127.0.0.1"  # proxies whose X-Forwarded-For is believed (Caddy's address)

    # worker
    alert_interval_s: int = 60
