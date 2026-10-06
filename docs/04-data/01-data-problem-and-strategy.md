# The data problem and the strategy

Status: Proposed. Decision recorded in [ADR-0002](../adr/0002-synthetic-first-training-data.md).

## What changed

The project plan listed "availability of historical data unknown" as a high-impact challenge, with "use public datasets as fallback" as the mitigation. That risk has now materialized in full: no client data exists and none will be provided. Three of our planned models depend on data:

| Model | Needs | What we had planned | What we have |
|---|---|---|---|
| Pest detector (US09, US10) | Labeled entrance images with Varroa, hornets, beetles | Public datasets + our camera | Public datasets of uneven quality and license, no camera yet |
| Anomaly detection (US16) | Months of hive telemetry with known events | Client history | Nothing |
| Yield prediction (US18 to US22) | Weight series with harvest records | Client history | Nothing |
| Swarm acoustics (REQ-05) | Labeled hive audio | Client recordings | Nothing, and no microphone on Prototype 1 |

## Options we considered

| Option | Verdict |
|---|---|
| Wait for data | Not possible. It will not come |
| Collect our own real data | Partly. We will capture what we can with the prototype, but we cannot wait a season for a swarm, and we cannot infest a hive with Varroa to get labels |
| Public datasets only | Not enough on their own. Licenses vary (some non-commercial, some GPL, some unclear), camera angles and resolution do not match our entrance setup, small hive beetle data barely exists, and there are no public long-term weight series with labeled events for tropical Africanized bees |
| Learned generative models (GANs, TimeGAN, diffusion trained on our data) | These learn to imitate a real dataset. With no real dataset, there is nothing to imitate. Popular tabular synthesizers such as SDV also moved to a source-available license, which rules them out |
| **Knowledge-driven simulation**, randomized, checked against real data where it exists | **Chosen.** We encode what is known about hives and about our sensors, randomize what is not known, and check the output against published measurements |

Simulation has a known weakness: a model can learn the simulator's quirks instead of the real phenomenon. The rest of this page is about containing that.

## Four data tiers

Every dataset, and every metric, belongs to exactly one tier.

| Tier | Name | Source | Used for | Never used for |
|---|---|---|---|---|
| S | Synthetic | Our generators | Training, development, regression tests of the pipeline, backend and dashboard development | Claiming the model works in the real world |
| P | Public real | Published datasets and openly licensed photos, license-checked | Validation and test of models trained on S; harvesting assets (cutouts, textures) when the license allows derivatives | Training the headline model (kept as a clean yardstick) |
| C | Team captures | Images and readings we record ourselves with the prototype or a phone: empty entrances, backgrounds, any bees we can film, DHT11 logs | Backgrounds and camera noise for the generator; a small realistic test set | |
| F | Field | The demo hive, if REQ-15 happens on a real colony | Final demo evaluation and the domain gap report | Tuning anything before the final evaluation |

Tier P is split in two before anyone looks at it: a calibration split, which we are allowed to look at while tuning the generators, and a test split that nobody opens until a model is frozen. Without this, we would slowly tune the simulator to the test set and the final number would mean nothing.

## How to make simulation trustworthy enough

1. Build from mechanisms, not from curve fitting. The telemetry simulator models why a hive's weight moves (foragers leave in the morning, nectar arrives in the afternoon, water evaporates at night) instead of drawing a curve that looks right. Mechanisms extrapolate to new weather; curve fits do not.
2. Randomize what we do not know. Colony strength, nectar availability, sensor bias, lighting, bee pose, mite position: anything we cannot pin down gets a range, and each sample draws from it. A model that works across the whole range has a better chance of covering the real hive somewhere inside it. In vision this is called domain randomization.
3. Use real inputs where they exist. Weather comes from real historical records for the region (Open-Meteo, built on ERA5 reanalysis), not from a weather model we invent. Image backgrounds come from photos we take of a real entrance board. Insect appearance comes from real photographs.
4. Model the sensor, not just the hive. A perfect 34.6 °C curve is not what the node reports. The DHT11 reports 35, or 33, or nothing. The node is offline for hours. Messages arrive twice. Models must learn from what the system will actually see. See [sensor and node realism](04-sensor-and-node-realism.md).
5. Check stylized facts. For each generator we list properties the real phenomenon is known to have (brood temperature stays within about 34 to 36 °C in a healthy colony; weight drops in the morning when foragers leave; a swarm removes roughly one to a few kilograms in minutes, usually around midday). Automated tests check that the generator reproduces them.
6. Report results per tier. "mAP@50 = 0.91 (tier S)" and "recall = 0.62 (tier P test)" are both useful. Mixing them up is the one mistake that would make the whole project's results misleading.

## What each team member gets out of this

| Who | Gets |
|---|---|
| Adrien (vision) | Unlimited labeled entrance images, with exact boxes, any class balance, any lighting |
| Diego (time series) | Years of telemetry per hive in minutes, with every swarm, harvest and sensor fault labeled to the minute |
| James (backend) | Fake nodes that publish over the real MQTT contract, including outages, duplicates and late data |
| Maria (frontend) | A populated system to design against, with alerts firing on schedule for demos |
| Ricardo (embedded) | A reference for what the node's output should look like, and test fixtures for the node software |
| Karen (communications) | Realistic message rates and backlog bursts to size the broker and test reconnection |

## Public data we can use for checking

Licenses must be confirmed on each dataset page before use. "Verify" means we could not confirm the license from the sources available while writing this; do not use the dataset until someone checks and records it in the asset manifest.

### Images

| Dataset | Content | Fit for us | License |
|---|---|---|---|
| VarroaDataset, TU Wien Computer Vision Lab ([Zenodo 4085044](https://zenodo.org/record/4085044)) | 13,509 bee crops (160 × 280 px), 3,947 with Varroa, 9,562 healthy, controlled environment, predefined splits | Good validation set for the stage 2 Varroa classifier | Verify |
| Bilik et al. 2021, "Visual diagnosis of the Varroa destructor parasitic mite in honeybees using object detector techniques" | 600 annotated images of healthy and infected bees in several scenes; YOLO and SSD baselines (F1 up to 0.874 for infected bees, 0.714 for mites) | Closest published setup to ours; good test set and baseline | Verify availability |
| Kaggle BeeImage dataset (Jenny Yang) | 5,100+ bee crops from time-lapse video, labeled with health status (including Varroa and hive beetles), subspecies, pollen | Varroa and beetle examples at entrance-like conditions | Verify |
| TensorFlow Datasets `bee_dataset` | Bee images labeled for Varroa, pollen, cooling, plus wasps | Extra Varroa examples and wasp negatives | GPL (per TFDS catalog) |
| BEEHIVE dataset ([Mendeley](https://data.mendeley.com/datasets/5yz78xxpmy)) | Close-range in-hive images, some with Varroa | Evaluation only | CC BY-NC: non-commercial, do not redistribute derivatives |
| Varroa on sticky boards ([Zenodo 10231845](https://zenodo.org/records/10231845)) | 64 very high resolution (8064 × 6048) images of mites on sticky boards, with labels | Source of high-resolution mite cutouts for the generator | Verify |
| VespAI (O'Shea-Wheller et al., Communications Biology 2024) | Hornet monitoring station images, *Vespa velutina* and *Vespa crabro* | Hornet appearance and the native-hornet false positive problem | Verify data availability |
| Insect Detect ([Zenodo 7725941](https://zenodo.org/records/7725941)) | Images for training an insect detector on a camera trap platform | Distractor insects (flies, other bees, beetles) | Verify |
| iNaturalist and Wikimedia Commons | Individual photos with per-image licenses (CC0, CC BY, CC BY-SA) | Main source of small hive beetle and hornet cutouts, since no SHB dataset exists | Per image; keep CC0 and CC BY |

### Telemetry and audio

| Dataset | Content | Fit for us |
|---|---|---|
| MSPB ([Zenodo 8371700](https://zenodo.org/records/8371700), Scientific Data 2024) | 53 hives in Québec, May 2020 to April 2021: audio, temperature, humidity, plus expert phenotypes (population, honey yield, swarming, Varroa) | Calibrate internal temperature and humidity dynamics and their link to colony events. Temperate climate, so seasonality does not transfer to Panama |
| Meikle et al. 2018, "Using within-day hive weight changes to measure environmental effects on honey bee colonies" (PLoS ONE) | Method and measurements of daily weight cycles | Shape and magnitude of the daily weight curve |
| "Modelling daily weight variation in honey bee hives" ([arXiv 2211.02335](https://arxiv.org/pdf/2211.02335)) | Model of forager departure, return and nightly loss | Direct input to the weight model |
| Nolasco and Benetos 2018, "To bee or not to bee" ([Zenodo 1321278](https://zenodo.org/record/1321278)) | Annotated beehive sounds | Acoustic work, if it happens |
| Open-Meteo historical API | Hourly reanalysis weather from 1940, global | Real weather input for the simulator. Data CC BY 4.0, server AGPL-3.0 and self-hostable |

## Rules

1. No dataset enters the repository or DVC without an entry in the manifest: source URL, license, who added it, date.
2. Non-commercial (NC) and unclear licenses: evaluation only, never redistributed, never baked into a published synthetic dataset.
3. Tier P test splits are created once, stored with a checksum, and opened only for final evaluation.
4. Generators are deterministic given a config and a seed.
5. Every chart, table and slide that shows a model metric names its tier.
