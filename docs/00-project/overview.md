# Project overview

Status: Accepted

## The problem

Most beekeepers judge the health of a colony by opening the hive and looking. Inspections are slow, they require travel to apiaries that are often remote, and every time the hive is opened the colony loses heat and gets stressed. The approach is also reactive. A Varroa infestation, a small hive beetle problem or a hornet hunting at the entrance is usually noticed after it has already done damage, and it does not scale when one person manages many colonies.

Two kinds of signal can tell a lot about a colony without opening it:

1. The internal climate. A healthy colony holds its brood nest at about 34 to 36 °C and keeps humidity in a narrow band. When thermoregulation slips, something is wrong: the colony is weak, queenless, or has left.
2. What happens at the entrance. Foragers come and go, intruders show up, and mites ride on returning bees.

Collecting these signals in the field is hard. The device sits outdoors in heat, high humidity and propolis, far from mains power, so it must run on batteries and do as much work as possible locally to save energy and bandwidth.

## What we are building

An IoT node that sits on a hive, measures temperature and humidity, captures images of the entrance, runs a pest detector locally, stores everything until it can be sent, and transmits the results to a server. The server stores the history, evaluates rules, raises alerts and serves a dashboard.

The detector output is decision support. A detection means "go and look", not "your hive has Varroa". The beekeeper always makes the call.

## Users

| Group | Who | What they need |
|---|---|---|
| Primary | Beekeepers with one or more colonies and mixed technical experience | Know when to visit a hive and why |
| Primary | Apiary administrators overseeing several sites | Compare colonies, see alert history |
| Secondary | Research organizations | Export clean, timestamped data |
| Secondary | Agricultural stakeholders | Better pollination management |

## Expected impact

- Fewer colony losses through early warning of pests, swarming and abnormal behavior.
- Harvest decisions based on data rather than calendar dates.
- Fewer trips to the apiary, which saves time and money.

## High-level requirements

These come from the project plan presentation. The [requirements document](../01-requirements/objectives-and-requirements.md) breaks them down.

1. Remote monitoring of weight, temperature, humidity, audio and an entrance camera, accessible from any device.
2. Honey yield prediction with harvest recommendations.
3. Swarm early warning, ideally 24 to 48 hours ahead (whether this is a hard requirement is an [open question](../01-requirements/elicitation-matrix.md), EL-13).
4. Pest and threat detection at the entrance: Varroa, small hive beetles, hornets and other intruders.
5. Configurable in-app and email alerts with thresholds and severity levels.
6. A colony dashboard with real-time status, trends and alert history.

The team has already agreed that one semester is not enough for three full ML systems. We are taking one capability end to end (pest detection on the edge, with sensor telemetry around it) and treating yield prediction and acoustic swarm detection as proofs of concept. See [risks](risks.md) and the [roadmap](../roadmap.md).

## Out of scope

- Commercial deployment.
- Installation across many apiaries.
- Any automatic action on the hive. The system recommends; the beekeeper decides.
- Collecting multi-season historical datasets.

The deliverable is a working demonstrator with an honest evaluation.

## The constraint that shapes everything: no data

At the start of the project we expected the client to provide historical hive data (weights, harvests, labeled audio, images). That data does not exist in a usable form and will not be provided. Every model in this project has to be trained on data we generate. This changes the plan in three ways:

- Data generation becomes a first-class engineering component, with its own code, tests and documentation ([docs/04-data](../04-data/README.md)).
- Evaluation must separate "works on our synthetic data" from "works on real images" ([vision evaluation](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/05-training-and-evaluation.md)).
- The same generator drives a hive simulator that lets the backend and frontend teams work before the hardware exists.
