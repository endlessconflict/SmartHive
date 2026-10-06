# Glossary

Status: Draft

## Beekeeping

| Term | Meaning |
|---|---|
| Absconding | The whole colony abandons the hive. More common in Africanized and tropical bees than in European bees. Shows up as a large weight drop and the internal temperature falling to ambient |
| Africanized honey bee | Hybrid of *Apis mellifera scutellata* with European subspecies. The dominant honey bee in Panama and Colombia; more defensive and more likely to abscond |
| Brood | Eggs, larvae and pupae. Kept at about 34 to 36 °C by the workers |
| Brood nest | Part of the hive where the brood is reared, usually the bottom box |
| Forager | Older worker bee that collects nectar, pollen, water and propolis |
| Honey flow (nectar flow) | Period when plants produce plenty of nectar and the hive gains weight quickly |
| Dearth | Period with little nectar; the hive lives on its stores and loses weight |
| Honey super (super) | Box added on top of the brood nest for the bees to store surplus honey |
| Landing board | Platform at the entrance where bees land and take off. Our camera looks at it |
| Phoretic mite | Varroa mite riding on an adult bee (as opposed to reproducing inside a capped brood cell). Only phoretic mites can be seen by an entrance camera |
| Queenless | Colony that has lost its queen. Changes its sound and, over weeks, its brood and temperature pattern |
| Robbing | Bees from another colony stealing honey. Heavy entrance traffic, weight loss during the day |
| Small hive beetle (SHB) | *Aethina tumida*, a 5 to 7 mm beetle whose larvae destroy comb and ferment honey |
| Swarming | Colony reproduction: the old queen leaves with a large part of the workers. Shows up as a sudden weight drop of one to a few kilograms, usually on a warm day around midday |
| Asian hornet | *Vespa velutina*, invasive predator that hunts bees in flight in front of the entrance |
| Varroa | *Varroa destructor*, a parasitic mite about 1.1 mm long and 1.6 mm wide. The main threat to honey bees worldwide |

## Technical

| Term | Meaning |
|---|---|
| ADR | Architecture decision record. A short document that records one decision and why |
| Domain gap / sim-to-real gap | Difference between the data a model was trained on and the data it sees in the field |
| Domain randomization | Varying lighting, textures, poses and noise in synthetic data so much that the real world looks like just another variation |
| DVC | Data Version Control, a tool that versions large data files next to git |
| Edge inference | Running a model on the device that captured the data, instead of on a server |
| Hypertable | TimescaleDB table automatically partitioned by time |
| Idempotent | Processing the same message twice has the same effect as processing it once |
| LWT | MQTT "last will and testament", a message the broker publishes when a client disconnects without saying goodbye |
| mAP@50, mAP@50:95 | Mean average precision of a detector at IoU threshold 0.5, and averaged over thresholds 0.5 to 0.95 |
| Motion gating | Running the expensive detector only when a cheap check says something moved |
| NCNN | Tencent's neural network inference library, optimized for ARM CPUs |
| QoS 0 / 1 | MQTT delivery levels: at most once / at least once (duplicates possible) |
| Store and forward | Keep data locally until the server confirms it has received it |
| TSTR | Train on synthetic, test on real. The only evaluation that says something about the real world |
