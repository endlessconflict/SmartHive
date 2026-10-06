# Tech stack

Status: Proposed

Owner: James Tack, with Maria de los Angeles Agudelo (DevOps)

Rules for every choice: an OSI-approved open-source license, no paid tier needed for our use, actively maintained, and boring enough that the team can find answers online. Licenses were checked when this page was written; re-check before adding anything new, because several well-known projects changed license recently.

## Languages

| Language | Where | Why |
|---|---|---|
| Python 3.11+ | Edge services, backend, simulators, training, ML jobs | One language for the node, the server and the AI work. Everyone on the team can read it |
| SQL (PostgreSQL dialect) | Migrations, time-bucket queries | Through SQLAlchemy and Alembic, with raw SQL where TimescaleDB functions are clearer |
| TypeScript | Dashboard | Types generated from the API's OpenAPI schema |
| JSON Schema | Message contracts | Single source of truth for MQTT payloads; Python and TypeScript types are generated from it |
| YAML | Configs (node, scenarios, generators, Compose) | |
| Bash | Small ops scripts | Keep it small; anything with logic becomes Python |
| C/C++ | Only if ESP32 sensor nodes are built later (ESP-IDF, Apache-2.0) | Not in Prototype 1 |

## Server

| Concern | Tool | License | Notes |
|---|---|---|---|
| Container runtime | Docker Engine + Compose plugin, or Podman + podman-compose | Apache-2.0 | Docker Desktop is proprietary; on Windows or macOS laptops use Podman Desktop (Apache-2.0) or a Linux VM |
| MQTT broker | Eclipse Mosquitto 2.x | EPL-2.0 / EDL-1.0 | Light, mature, TLS, ACLs, persistence, last will |
| Database | PostgreSQL 16 or 17 | PostgreSQL License | |
| Time-series extension | TimescaleDB, Apache-2.0 edition | Apache-2.0 | Hypertables and `time_bucket`. Compression, continuous aggregates and retention policies are under the Timescale License, which is not OSI-approved, so we do not use them. See [ADR-0005](../adr/0005-postgresql-timescaledb-apache.md) |
| Web framework | FastAPI | MIT | Async, typed, generates OpenAPI for the frontend |
| ASGI server | Uvicorn | BSD-3 | |
| Validation and settings | Pydantic v2, pydantic-settings | MIT | Shared between ingestor, API and simulator |
| ORM and migrations | SQLAlchemy 2.x, Alembic | MIT | |
| PostgreSQL driver | asyncpg | Apache-2.0 | Also used directly for `LISTEN/NOTIFY` |
| MQTT client (server) | aiomqtt (on top of paho-mqtt) | BSD-3 (paho: EPL-2.0 / EDL-1.0) | |
| JSON Schema | jsonschema; datamodel-code-generator | MIT | Validate payloads; generate Pydantic models from schemas |
| Password hashing | argon2-cffi | MIT | |
| Tokens | PyJWT | MIT | Short-lived access tokens |
| Scheduling | APScheduler | MIT | Inside the worker |
| HTTP client | httpx | BSD-3 | Open-Meteo, ntfy |
| Email | aiosmtplib + Jinja2 templates | MIT / BSD-3 | Any SMTP account the team already has |
| Push notifications (optional) | ntfy, self-hosted | Apache-2.0 / GPL-2.0 | Phone notifications without Firebase accounts |
| Reverse proxy, TLS | Caddy | Apache-2.0 | Serves the dashboard, proxies API and WebSocket; internal CA for the LAN |
| Time server | chrony | GPL-2.0 | The Pi has no real-time clock |
| Local email testing | Mailpit | MIT | Catches outgoing mail in development |
| Weather data | Open-Meteo API | Server AGPL-3.0, data CC BY 4.0 | Free for non-commercial use without an API key; self-hostable |

## Edge node

| Concern | Tool | License |
|---|---|---|
| OS | Raspberry Pi OS Lite 64-bit | FOSS (Debian-based) |
| Process supervision | systemd units with `MemoryMax=` | LGPL-2.1+ |
| Local store-and-forward | SQLite (WAL mode) via Python's `sqlite3` | Public domain |
| MQTT client | paho-mqtt | EPL-2.0 / EDL-1.0 |
| HTTP client | httpx | BSD-3 |
| DHT11 | Linux kernel IIO driver (`dtoverlay=dht11`) | GPL-2.0 |
| HX711 (later) | Small Python driver over `gpiod` | LGPL-2.1+ (libgpiod) |
| Camera | picamera2 (CSI) or OpenCV V4L2 (USB) | BSD-2 / Apache-2.0 |
| Image ops | OpenCV headless, NumPy | Apache-2.0 / BSD-3 |
| Inference | NCNN (fallback: ONNX Runtime) | BSD-3 / MIT |
| Provisioning | Ansible (from a laptop) | GPL-3.0 |
| Logs | journald, volatile storage | LGPL-2.1+ |

## Data, simulation and ML

| Concern | Tool | License |
|---|---|---|
| Numerics | NumPy, SciPy, pandas or Polars | BSD-3 / MIT |
| Columnar files | Apache Arrow / Parquet (pyarrow) | Apache-2.0 |
| Training | PyTorch, torchvision | BSD-3 |
| Detector and classifier training | Ultralytics YOLO11 (AGPL-3.0), chosen in [ADR-0008](../adr/0008-detector-licensing.md) | AGPL-3.0 |
| Model export | pnnx and ncnn (through Ultralytics' ncnn export) | BSD-3 |
| Segmentation for cutouts (only if real cutouts are added later) | SAM 2 | Apache-2.0 |
| Dataset browsing (planned) | FiftyOne | Apache-2.0 |
| Annotation of real images | Label Studio or CVAT | Apache-2.0 / MIT |
| Synthetic images | Own procedural renderer: NumPy + OpenCV ([ADR-0009](../adr/0009-procedural-insect-rendering.md)) | Apache-2.0 / BSD |
| Real-image check set | iNaturalist Open Dataset on AWS, CC0/CC-BY photos only | per photo |
| 3D rendering (optional) | Blender, BlenderProc | GPL |
| Classical ML, anomaly baselines | scikit-learn | BSD-3 |
| Forecasting (Epic 4) | statsmodels; LightGBM | BSD-3 / MIT |
| Data versioning (planned, EN-06) | DVC | Apache-2.0 |
| Experiment tracking (planned; runs currently write a JSON summary) | MLflow (file or SQLite backend) | Apache-2.0 |
| Notebooks | JupyterLab | BSD-3 |

## Quality, CI and docs

| Concern | Tool | License |
|---|---|---|
| Lint and format | Ruff | MIT |
| Type checking | mypy | MIT |
| Tests | pytest, pytest-asyncio | MIT / Apache-2.0 |
| Integration tests with real services | Testcontainers for Python | Apache-2.0 |
| Pre-commit hooks | pre-commit | MIT |
| Markdown lint | markdownlint-cli2 | MIT |
| Diagrams | Mermaid (rendered by GitHub) | MIT |
| CI | GitHub Actions | Service, not FOSS; free for public repositories. FOSS alternative if needed: Forgejo with Woodpecker CI (GPL-3.0 / Apache-2.0) |
| Monitoring (optional) | Prometheus, Grafana | Apache-2.0 / AGPL-3.0 |

## Frontend (to be decided by Maria)

Proposed candidates, all MIT or Apache-2.0: SvelteKit or React with Vite; Apache ECharts or uPlot for time-series charts; openapi-typescript to generate the API client. The framework decision belongs to the frontend owner and is scheduled in the [roadmap](../roadmap.md).

## Considered and not used

| Tool | Reason |
|---|---|
| MinIO | The community edition stopped shipping binaries and Docker images in October 2025, entered maintenance mode in December 2025 and its repository was archived in February 2026. Not a safe base. If we ever need S3-compatible storage: SeaweedFS (Apache-2.0) or Garage (AGPL-3.0) |
| InfluxDB | InfluxDB 3 Core is MIT/Apache-2.0 and would work, but it would be a second database next to PostgreSQL, which we need anyway for users, hives and alerts. Version 3 Core also limits how many Parquet files one query may touch (432 by default), which affects long-range queries |
| TimescaleDB TSL features | Compression, continuous aggregates and retention policies are under the Timescale License, which is source-available, not OSI open source |
| Redis | Not needed (PostgreSQL `LISTEN/NOTIFY` is enough). Redis changed license in 2024 and added AGPL-3.0 as an option in 2025; if a cache is ever needed, Valkey (BSD-3) is the community fork |
| SDV (Synthetic Data Vault) | Business Source License, not open source. Also needs real data to learn from |
| Stable Diffusion checkpoints under OpenRAIL licenses | Use restrictions make them not OSI open source |
| Firebase Cloud Messaging, Twilio SMS | Proprietary services; SMS also costs money |
| Kubernetes | Far more than one Compose file needs |
