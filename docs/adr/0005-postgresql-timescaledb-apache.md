# ADR-0005: PostgreSQL with TimescaleDB, Apache-2.0 features only

Status: Proposed
Date: 2026-10-06
Deciders: James Tack, Diego Alejandro Vasquez, Maria de los Angeles Agudelo

## Context

We store relational data (users, apiaries, hives, nodes, alerts) and time series (readings, health, summaries). The original proposal listed InfluxDB or TimescaleDB. Volume is small: about 2.6 million readings per hive per year at one reading per minute for five quantities. The project must use only OSI-approved licenses.

TimescaleDB ships two editions. The Apache-2.0 edition includes hypertables, `time_bucket` and `drop_chunks`. Compression, continuous aggregates and automatic retention policies are under the Timescale License, which is source-available, not open source.

## Decision

One database: PostgreSQL 16 or later with the TimescaleDB extension, using only Apache-2.0 features (the `-oss` image). Downsampling happens at query time with `time_bucket`; retention runs from our scheduler with `drop_chunks`.

## Alternatives considered

| Option | Why not |
|---|---|
| InfluxDB 3 Core (MIT/Apache-2.0) | Would be a second database next to PostgreSQL, a second query language, a second backup. Also limits the number of Parquet files a query may scan (432 by default), which affects long ranges |
| InfluxDB 2.x | Older line; same two-database problem |
| Plain PostgreSQL without TimescaleDB | Works at our scale and is the fallback if the extension causes trouble. Hypertables make chunk management and time bucketing simpler |
| TimescaleDB Community (TSL) features | Not OSI open source |

## Consequences

- Joins between readings and hive metadata are plain SQL.
- If the system grows far beyond a demonstrator, compression or continuous aggregates may be wanted; that would need a license decision or a different approach (materialized views refreshed by our scheduler).
