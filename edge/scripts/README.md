# edge/scripts/

`fake_telemetry.py` connects to the broker as one or more fake nodes and publishes DHT11-like telemetry with Gaussian noise, to test the backend (ingestor, database, live feed, dashboard) without hardware.

Each reading is `mean + N(0, sd)`: by default 35 ± 0.8 degC and 58 ± 3 %RH (a brood nest). `--dht11` rounds and clips like the real sensor (values outside the range get `quality: clipped`), `--fail-p` adds read errors, `--batch` sends several samples per message like a node draining its queue, `--seed` makes a run repeatable.

```bash
pip install -r edge/scripts/requirements.txt

# Compose broker, mutual TLS. Each fake node needs its own certificate (CN = node id):
(cd infra/pki && ./gen_certs.sh sim-0001 sim-0002)
python edge/scripts/fake_telemetry.py --host localhost --pki infra/pki --nodes sim-0001 sim-0002 --interval 5 --dht11

# Plain broker on 1883
python edge/scripts/fake_telemetry.py --no-tls --interval 1 --count 20

# Only print the payloads
python edge/scripts/fake_telemetry.py --dry-run --count 2 --fail-p 0.2
```

Use node ids with the `sim-` prefix: the backend marks those nodes as simulated, so test data never mixes with real hives. `python edge/scripts/fake_telemetry.py -h` lists every option.
