# ADR-0001: Record architecture decisions

Status: Accepted
Date: 2026-10-06
Deciders: whole team

## Context

Six people are building parts of one system in parallel, across hardware, communications, backend, AI and frontend. Decisions made in meetings or chats get forgotten or remembered differently, and the next person to touch the code cannot tell whether a choice was deliberate.

## Decision

We record decisions that are expensive to reverse as ADRs in `docs/adr/`, using the template. An ADR is short, lists the alternatives we rejected, and is never rewritten after acceptance: a new ADR supersedes it.

## Consequences

Writing an ADR takes half an hour. In exchange, reviews, the final report and new contributors have one place to see why the system looks the way it does.
