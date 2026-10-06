# Risk register

Status: Proposed (updated after the decision to use synthetic data)

The first five rows come from the project plan presentation. The rest were added while designing the data pipeline and the backend. Owners are suggestions for the next planning meeting.

| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | No historical data for training | High | **Happened** | Done: telemetry simulator and procedural image generator in the repo; real iNaturalist photos kept for validation only ([04-data](../04-data/01-data-problem-and-strategy.md), [ADR-0009](../adr/0009-procedural-insect-rendering.md)) | Adrien, Diego |
| R2 | Hardware delivery delays block node development | High | Medium | Hive simulator that publishes on the real MQTT contract; node software developed on any Linux machine with mocked sensors | Ricardo, James |
| R3 | No reliable cellular coverage at the apiary | Medium | Unknown | Prototype 1 uses Ethernet. Message format kept small enough for LoRaWAN later | Karen |
| R4 | Scope too broad for one semester (three ML systems) | High | High | Pest detection end to end; yield and acoustics as proofs of concept | Adrien (PO) |
| R5 | Integration failures found late | High | Medium | Contracts frozen in docs, contract tests in CI, end-to-end demo every sprint | James, Maria |
| R6 | Model works on synthetic images and fails on real ones (sim-to-real gap) | High | High | Measured every iteration on the frozen iNaturalist test ([results](../03-vision/07-results.md)); real board backgrounds next; results always reported per data tier | Adrien |
| R7 | Varroa too small to see at the chosen camera resolution | High | Medium | Resolution calculation before choosing the camera; two-stage model that crops bees from the full-resolution frame | Adrien, Ricardo |
| R8 | Raspberry Pi 3B too slow or short of memory (1 GB) for the detector | Medium | Medium | Motion gating, 320 px detector input, INT8 models, NCNN runtime; benchmark spike before committing | Adrien |
| R9 | Battery autonomy of about one day with a Pi always on | Medium | High | Measure real consumption; decide autonomy target with the client; options are solar, power gating or mains for the demo. Backend tolerant to daily gaps | Ricardo |
| R10 | Wrong timestamps after a cold boot (the Pi has no real-time clock) | Medium | High | NTP from the gateway, `clock_synced` flag on every reading, optional RTC module | Ricardo, Karen |
| R11 | License trouble: a component turns out to be non-FOSS or incompatible | Medium | Medium | License column in the stack document; asset manifest for every external image or model; ADR-0008 on detector licensing | Maria |
| R12 | Client never answers the elicitation questions | High | Medium | Each open question has a documented default assumption so work can continue; defaults flagged in the demo | Adrien (PO) |
| R13 | DHT11 imprecision makes subtle anomalies undetectable | Medium | High | Simulator reproduces DHT11 limits so models are trained on realistic precision; recommend a better sensor if one is available | Diego, Ricardo |
| R14 | microSD card corruption from power loss or write wear | Medium | Medium | SQLite in WAL mode, fewer log writes, read-only root as a stretch goal; backups of the card image | Ricardo |

## How to use this table

Review it at every retrospective. When a risk happens, mark it, link the issue, and say what the mitigation actually did. Remove a risk only when the thing that caused it is gone.
