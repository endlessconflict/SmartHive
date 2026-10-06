# ADR-0003: Raspberry Pi 3B as the Prototype 1 edge node

Status: Proposed
Date: 2026-10-06
Deciders: Ricardo Villarreal, Adrien Cubilla, Karen Jimenez

## Context

Two node designs are in circulation. The project plan and the first backlog item describe an ESP32 node talking LoRaWAN. The design document and the electrical schematic describe a Raspberry Pi 3B with a DHT11 and a camera, connected by Ethernet to a gateway, powered by a 3S2P Li-ion pack through an MP1584 buck converter. Requirements FR-05 and US11 ask for image processing on the node.

## Decision

Prototype 1 is the Raspberry Pi 3B design from the electrical schematic. All node software targets it: Raspberry Pi OS Lite 64-bit, Python services under systemd, NCNN for inference, Ethernet to the gateway.

The backend does not assume the sender is a Pi. A future ESP32 sensor node (weight, climate, low power) can publish the same messages, through a LoRaWAN network server if needed.

## Alternatives considered

| Option | Why not, for Prototype 1 |
|---|---|
| ESP32 only | Cannot run a bee detector plus a Varroa classifier on high-resolution crops. Would push image analysis to the server, contradicting FR-05, and images cannot be sent over LoRaWAN |
| ESP32-S3 or ESP32-CAM with a tiny model | Possible for a coarse "hornet present" classifier, not for Varroa at the required resolution |
| Raspberry Pi 4 or 5 | Faster and more memory, but not the hardware we have, and there is no budget |
| Pi plus ESP32 split node | Best power profile. More integration work than one semester allows; kept in the roadmap for Prototype 2 |

## Consequences

- 1 GB of RAM: no Docker or PyTorch on the node, memory limits per service, small models.
- No sleep mode: battery autonomy is about one day ([power budget](../02-hardware/power-budget.md)).
- No RTC: timestamps need NTP from the gateway and a `clock_synced` flag.
- The presentation and backlog should be updated so they match this design.
