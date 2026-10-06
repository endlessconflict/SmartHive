# Scenarios and events

Status: Proposed

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
| `supersedure` | Queen replaced by a new one | Slightly lower gains for a few weeks | Brief brood gap | | | Start, end |
| `robbing` | Other colonies steal honey | Unusual weight loss during the afternoon on flight days, 0.2 to 2 kg/day | Normal | Normal | Very high | Start, end, daily loss |
| `starvation_risk` | Stores fall low during a dearth | Steady decline, `S` below threshold | Regulation loosens as the colony weakens | | Lower | Start (when `S` crosses threshold) |
| `colony_collapse` | Gradual decline to death (from disease, pests...) | Daily cycle shrinks over weeks | `γ` rises steadily, then ambient | | Falls to zero | Start, end |

### Management events (the beekeeper)

| Type | Weight | Temperature | Notes |
|---|---|---|---|
| `inspection` | Spike and dip of a few kg over 5 to 30 min (hands, lid, frames out), back to baseline | Drop of 1 to 4 °C, recovers within an hour | Must not be flagged as an anomaly. The dashboard should let the beekeeper log visits so the backend can mask them |
| `super_added` | Step up equal to the empty super | Small dip | Input to Epic 4 |
| `harvest` | Step down of several kg during a visit | Like an inspection | Yield ground truth for Epic 4 |
| `feeding` | Step up by the syrup mass, then gradual decrease as it is stored and consumed | | |
| `treatment` | Small step (strips, trays) | Possible small change | |

### Sensor and node events

Described in [sensor and node realism](04-sensor-and-node-realism.md). They are labeled too, because an anomaly detector must learn to tell "the hive is in trouble" from "the sensor is in trouble".

| Type | Effect |
|---|---|
| `sensor_dropout` | Readings missing for minutes to hours |
| `sensor_stuck` | Same value repeated |
| `sensor_drift` | Slow bias change |
| `sensor_spike` | Isolated outliers |
| `node_offline` | All channels missing, data arrives later in a burst (or never, if the outage outlasts the local buffer) |
| `clock_jump` | Timestamps shifted after a cold boot without NTP |
| `scale_creep` | Load cell slowly drifts under constant load (when weight exists) |

## Event rates

Each scenario includes an events file with a rate per type and per season. Defaults:

```yaml
# events/default_rates.yaml  (rates per hive; values are starting assumptions)
swarm:            {per_year: 0.6, season: flow, daytime: [9, 15], requires: [queen_present, strong_colony]}
absconding:       {per_year: 0.15}
queen_loss:       {per_year: 0.2}
robbing:          {per_year: 0.3, season: dearth}
inspection:       {every_days: {dist: uniform, low: 7, high: 21}, daytime: [8, 16]}
super_added:      {rule: "S > 0.7 * capacity and season == flow"}
harvest:          {rule: "supers_full and season_end"}
sensor_dropout:   {per_week: 1.0, duration_min: {dist: lognormal, median: 20, sigma: 1.2}}
sensor_stuck:     {per_year: 2}
node_offline:     {per_week: 0.5, duration_h: {dist: lognormal, median: 3, sigma: 1.0}}
```

Rare events can be oversampled for training datasets (for example "every hive swarms once in this dataset") while test datasets keep realistic rates. Both versions are written down in the dataset card.

## Named scenarios

| Scenario | Purpose | Hives × duration |
|---|---|---|
| `panama_baseline` | Normal year, default rates. General training and dashboard demos | 20 × 2 years |
| `swarm_season` | Oversampled swarms during the flow | 50 × 4 months |
| `abscond_and_collapse` | Oversampled absconding and slow collapse | 30 × 6 months |
| `sensor_hell` | Very high rate of every sensor and node fault | 10 × 3 months |
| `quiet_hive` | No events at all. Baseline for false-positive rates | 10 × 1 year |
| `demo_day` | A scripted day with one swarm at 11:00, a hornet detection at 14:00 and a node dropout at 16:00, replayed over MQTT at 1× for the final demo | 1 × 1 day |

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
