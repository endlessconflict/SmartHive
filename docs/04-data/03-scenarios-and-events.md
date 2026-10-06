# Scenarios and events

Status: Implemented in the simulator v1.0.0, except where marked "planned"

Owner: Diego Alejandro Vasquez

Events are what the models exist to find. In real data they are rare, unlabeled and impossible to schedule. In the simulator we choose when they happen, how strong they are, and we know their exact start and end. This page lists the events, how each one changes the signals, and how they are used for training and testing.

## Event catalog

Signatures describe the true signal. The sensor model is applied afterwards. Magnitudes are ranges sampled per event; where a number comes from literature it is cited in [references](../references.md), and the rest are starting assumptions to review.

### Colony events

| Type | What happens | Weight | Temperature (brood probe) | Humidity | Traffic | Labels |
|---|---|---|---|---|---|---|
| `swarm` | Old queen leaves with a large share of workers | Drop of 1 to 4 kg within 10 to 30 min, usually 09:00 to 15:00, warm day, during a flow. Afternoon gains smaller for weeks after | Small disturbance, then normal; brood still present | Small change | Burst during the event, lower after | Start, end, kg lost, share of `N` lost |
| `absconding` | Whole colony leaves (common in Africanized bees) | Drop of most of the bee mass plus some stores; no more daily cycle | Converges to ambient within hours | Tracks ambient | Burst, then near zero | Start, end |
| `queen_loss` | Queen dies, no immediate replacement | No immediate change | Normal while capped brood remains (about 3 weeks), then looser regulation (`γ` up, `T_set` down) | Slowly less regulated | Slowly lower | Start (hidden in signals for weeks) |
| `supersedure` (planned) | Queen replaced by a new one | Slightly lower gains for a few weeks | Brief brood gap | | | Start, end |
| `robbing` | Other colonies steal honey | Unusual weight loss during the afternoon on flight days, 0.2 to 2 kg/day | Normal | Normal | Very high | Start, end, daily loss |
| `starvation_risk` (planned label; starvation itself is modeled) | Stores fall low during a dearth | Steady decline, `S` below threshold | Regulation loosens as the colony weakens | | Lower | Start (when `S` crosses threshold) |
| `colony_collapse` (emerges from queen loss or starvation; no separate label yet) | Gradual decline to death (from disease, pests...) | Daily cycle shrinks over weeks | `γ` rises steadily, then ambient | | Falls to zero | Start, end |

### Management events (the beekeeper)

| Type | Weight | Temperature | Notes |
|---|---|---|---|
| `inspection` | Spike and dip of a few kg over 5 to 30 min (hands, lid, frames out), back to baseline | Drop of 1 to 4 °C, recovers within an hour | Must not be flagged as an anomaly. The dashboard should let the beekeeper log visits so the backend can mask them |
| `super_added` | Step up equal to the empty super | Small dip | Input to Epic 4 |
| `harvest` | Step down of several kg during a visit | Like an inspection | Yield ground truth for Epic 4 |
| `feeding` | Step up of 3 to 5 kg of syrup, then consumed like stores. The simulated beekeeper feeds at an inspection when honey falls below 2 kg | | Keeps colonies alive through the dearth |
| `treatment` (planned) | Small step (strips, trays) | Possible small change | |

### Sensor and node events

Described in [sensor and node realism](04-sensor-and-node-realism.md). They are labeled too, because an anomaly detector must learn to tell "the hive is in trouble" from "the sensor is in trouble".

| Type | Effect |
|---|---|
| `sensor_dropout` | Readings missing for minutes to hours |
| `sensor_stuck` | Same value repeated |
| `sensor_drift` | Slow bias change (humidity fouling is modeled, not labeled) |
| `sensor_spike` | Isolated outliers (load cell spikes are modeled, not labeled) |
| `node_offline` | All channels missing, data arrives later in a burst (or never, if the outage outlasts the local buffer) |
| `clock_jump` | Timestamps shifted after a cold boot without NTP (rows flagged `clock_unsynced` with `clock_offset_s`) |
| `scale_creep` | Load cell slowly drifts under constant load (modeled, not labeled) |

## Event rates

Each scenario includes an events file with a rate per type and per season. Defaults:

Defaults in `simulation/telemetry/sim.py` (`DEFAULTS`), overridden per scenario:

```yaml
events:
  swarm_per_year: 0.6        # weighted towards the flow; needs a laying queen, N > 20,000, bloom > 0.3; 10:00-14:00
  abscond_per_year: 0.15     # needs N > 1,000
  queen_loss_per_year: 0.2
  robbing_per_year: 0.3      # weighted towards the dearth; 2-5 days, 13:00-17:00
  inspection_every_days: [7, 21]
  supers: true               # added when honey > 70 % of capacity during a flow (max 3)
  harvest: true              # when the flow ends and honey > 12 kg; leaves 8-12 kg
  feed_below_kg: 2.0
sensor: {read_fail_p: 0.04, stuck_per_year: 2, dropout_per_week: 1.0}
node:   {power: mains, outage_per_week: 0.5, outage_median_h: 3}
```

Rare events can be oversampled for training datasets (for example "every hive swarms once in this dataset") while test datasets keep realistic rates. Both versions are written down in the dataset card.

## Named scenarios

| Scenario | Purpose | Hives × duration |
|---|---|---|
| `panama_baseline` | Normal years, default rates. General training and dashboard demos | 20 × 2 years |
| `swarm_season` | Oversampled swarms during the flow | 50 × 4 months |
| `abscond_and_collapse` | Oversampled absconding and queen loss | 30 × 6 months |
| `sensor_hell` | Very high rate of every sensor and node fault | 10 × 3 months |
| `quiet_hive` | No colony events. Baseline for false-positive rates | 10 × 1 year |
| `battery_node` | Battery-only node swapped daily at 09:00, 1-minute step | 3 × 30 days |
| `demo_day` (planned with the MQTT replay) | A scripted day with one swarm at 11:00, a hornet detection at 14:00 and a node dropout at 16:00, replayed at 1× for the final demo | 1 × 1 day |

Event counts in `panama_baseline`, seed 42 (20 hives, 2 years): 12 swarms, 4 absconding, 3 queen losses, 10 robbing episodes, 1,028 inspections, 42 supers added, 24 harvests (median 17.8 kg), 124 feedings, plus 2,082 sensor dropouts, 81 stuck-sensor episodes and 1,044 node outages.

## How the events are used

### For anomaly detection (US16, US17)

US16 asks the system to flag unusual behavior "that does not match any known pattern". To test that honestly, some event types must be absent from training:

| Split | Hives | Event types present |
|---|---|---|
| Train | 60 % of hives | `swarm`, `robbing`, `inspection`, `harvest`, sensor faults |
| Validation | 20 % of hives | Same as train |
| Test (known) | 20 % of hives | Same as train |
| Test (novel) | Separate scenario | `absconding`, `queen_loss`, `colony_collapse` never seen in training |

Splits are by hive, never by time within a hive, so the model cannot learn a hive's individual quirks from training and recognize them in test.

Metrics are event-level, because that is what the beekeeper experiences:

- Event recall: share of events with at least one alert inside the event window (plus a tolerance).
- Detection delay: time from event start to first alert.
- False alerts per hive per week, measured on `quiet_hive`.
- Separately for sensor faults: does the model call them sensor problems or hive problems?

### For yield prediction (US18 to US22)

Ground truth comes from the colony state: net gain in `S` over the next 7 days, excluding management steps. EL-10 may redefine "yield"; if so, only the label function changes. Baselines to beat: "same as last week" and "seasonal average from the simulated history". A model that cannot beat those on synthetic data will not beat them on a real hive.

### For the backend and the dashboard

The replay tool publishes events as they happen. Alert rules can be tested against known truth: did the swarm at 11:00 produce an alert, how long did it take, and did the inspection at 14:00 produce a false one?

## Adding a new event type

1. Write the signature (which signals change, how, with what ranges) in this page, with a reference if one exists.
2. Implement it in `simulation/telemetry/events/` as a function that takes the state and parameters and returns modifications plus a label.
3. Add a stylized-fact test.
4. Bump the generator's minor version, since datasets generated before do not contain it.
