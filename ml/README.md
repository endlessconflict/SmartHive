# ml/

Time-series models: anomaly detection (US16, US17) and, if time allows, honey yield prediction and harvest recommendations (Epic 4).

Status: Planned. Training data comes from the telemetry simulator; see [docs/04-data/](../docs/04-data/README.md). Model design is scheduled in the [roadmap](../docs/roadmap.md).

Planned layout:

```text
ml/
├── features/             Daily features from telemetry (weight deltas, thermal stability...)
├── anomaly/              Unsupervised and rule-based baselines
├── yield/                7-day yield forecast with prediction intervals
├── eval/                 Event-level metrics on labeled synthetic scenarios
└── jobs/                 Entry points the backend worker schedules
```

Owner: Diego Alejandro Vasquez.
