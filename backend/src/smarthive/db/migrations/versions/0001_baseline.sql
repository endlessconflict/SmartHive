CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE users (
  id            uuid PRIMARY KEY,
  email         citext UNIQUE NOT NULL,
  display_name  text NOT NULL,
  password_hash text NOT NULL,
  role          text NOT NULL CHECK (role IN ('beekeeper', 'admin')),
  notify_email  boolean NOT NULL DEFAULT true,
  ntfy_topic    text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE apiaries (
  id        uuid PRIMARY KEY,
  owner_id  uuid NOT NULL REFERENCES users(id),
  name      text NOT NULL,
  lat       double precision,
  lon       double precision,
  timezone  text NOT NULL DEFAULT 'America/Panama'
);

CREATE TABLE hives (
  id           uuid PRIMARY KEY,
  apiary_id    uuid NOT NULL REFERENCES apiaries(id),
  name         text NOT NULL,
  hive_type    text,
  boxes        smallint,
  installed_on date,
  notes        text,
  archived     boolean NOT NULL DEFAULT false
);

CREATE TABLE nodes (
  id            text PRIMARY KEY,
  is_simulated  boolean NOT NULL,
  device_token_hash text NOT NULL,
  hardware      jsonb NOT NULL DEFAULT '{}',
  registered_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz,
  status        text NOT NULL DEFAULT 'unknown'
);

CREATE TABLE node_assignments (
  node_id   text NOT NULL REFERENCES nodes(id),
  hive_id   uuid NOT NULL REFERENCES hives(id),
  valid     tstzrange NOT NULL,
  EXCLUDE USING gist (node_id WITH =, valid WITH &&)
);

CREATE TABLE readings (
  ts            timestamptz NOT NULL,
  node_id       text NOT NULL,
  hive_id       uuid,
  quantity      text NOT NULL,
  value         double precision,
  quality       text NOT NULL,
  sensor        text NOT NULL,
  clock_synced  boolean NOT NULL,
  msg_id        uuid NOT NULL,
  idx           smallint NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (msg_id, idx, ts)
);
SELECT create_hypertable('readings', 'ts', chunk_time_interval => interval '7 days');
CREATE INDEX ON readings (hive_id, quantity, ts DESC);

CREATE TABLE node_health (
  ts       timestamptz NOT NULL,
  node_id  text NOT NULL,
  data     jsonb NOT NULL,
  PRIMARY KEY (node_id, ts)
);
SELECT create_hypertable('node_health', 'ts', chunk_time_interval => interval '7 days');

CREATE TABLE weather (
  ts         timestamptz NOT NULL,
  apiary_id  uuid NOT NULL REFERENCES apiaries(id),
  temp_c double precision, rh_pct double precision, precip_mm double precision,
  wind_ms double precision, radiation_wm2 double precision,
  source     text NOT NULL,
  PRIMARY KEY (apiary_id, ts, source)
);

CREATE TABLE images (
  id           uuid PRIMARY KEY,
  node_id      text NOT NULL REFERENCES nodes(id),
  hive_id      uuid,
  captured_at  timestamptz NOT NULL,
  clock_synced boolean NOT NULL,
  reason       text NOT NULL,
  path         text NOT NULL,
  sha256       text NOT NULL,
  bytes        integer NOT NULL,
  width        integer, height integer,
  objects      jsonb NOT NULL DEFAULT '[]',
  received_at  timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz
);

CREATE TABLE detection_events (
  msg_id       uuid PRIMARY KEY,
  episode_id   uuid NOT NULL,
  node_id      text NOT NULL REFERENCES nodes(id),
  hive_id      uuid,
  type         text NOT NULL,
  cls          text,
  first_seen   timestamptz NOT NULL,
  last_seen    timestamptz NOT NULL,
  max_conf     real,
  frames_positive smallint, frames_window smallint,
  image_id     uuid,
  models       jsonb,
  received_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON detection_events (hive_id, first_seen DESC);

CREATE TABLE vision_summaries (
  node_id      text NOT NULL,
  hive_id      uuid,
  window_start timestamptz NOT NULL,
  window_end   timestamptz NOT NULL,
  frames_analyzed integer NOT NULL,
  counts       jsonb NOT NULL,
  varroa_classified integer NOT NULL,
  varroa_positive   integer NOT NULL,
  msg_id       uuid NOT NULL UNIQUE,
  PRIMARY KEY (node_id, window_start)
);

CREATE TABLE alert_rules (
  id         text PRIMARY KEY,
  enabled    boolean NOT NULL DEFAULT true,
  severity   text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  params     jsonb NOT NULL DEFAULT '{}',
  hive_id    uuid REFERENCES hives(id)
);

CREATE TABLE alerts (
  id          uuid PRIMARY KEY,
  hive_id     uuid REFERENCES hives(id),
  node_id     text REFERENCES nodes(id),
  rule_id     text NOT NULL,
  severity    text NOT NULL,
  state       text NOT NULL CHECK (state IN ('open', 'acknowledged', 'resolved')),
  title       text NOT NULL,
  details     jsonb NOT NULL,
  dedup_key   text NOT NULL,
  opened_at   timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  acknowledged_at timestamptz, acknowledged_by uuid REFERENCES users(id),
  resolved_at timestamptz, resolved_by uuid REFERENCES users(id),
  resolution_note text
);
CREATE UNIQUE INDEX one_open_alert_per_key ON alerts (dedup_key) WHERE state <> 'resolved';

CREATE TABLE alert_events (
  id        bigserial PRIMARY KEY,
  alert_id  uuid NOT NULL REFERENCES alerts(id),
  at        timestamptz NOT NULL DEFAULT now(),
  kind      text NOT NULL,
  actor     uuid REFERENCES users(id),
  data      jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE notifications (
  id        bigserial PRIMARY KEY,
  alert_id  uuid NOT NULL REFERENCES alerts(id),
  user_id   uuid NOT NULL REFERENCES users(id),
  channel   text NOT NULL,
  status    text NOT NULL,
  attempts  smallint NOT NULL DEFAULT 0,
  sent_at   timestamptz, error text,
  read_at   timestamptz
);

CREATE TABLE management_events (
  id        uuid PRIMARY KEY,
  hive_id   uuid NOT NULL REFERENCES hives(id),
  type      text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at   timestamptz,
  data      jsonb NOT NULL DEFAULT '{}',
  created_by uuid REFERENCES users(id)
);

CREATE TABLE anomalies (
  id        uuid PRIMARY KEY,
  hive_id   uuid NOT NULL REFERENCES hives(id),
  period    tstzrange NOT NULL,
  score     real NOT NULL,
  kind      text,
  model     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE predictions (
  hive_id   uuid NOT NULL REFERENCES hives(id),
  made_at   timestamptz NOT NULL,
  target    text NOT NULL,
  horizon   interval NOT NULL,
  p10 real, p50 real, p90 real,
  model     text NOT NULL,
  PRIMARY KEY (hive_id, target, made_at)
);

CREATE TABLE commands (
  id         uuid PRIMARY KEY,
  node_id    text NOT NULL REFERENCES nodes(id),
  name       text NOT NULL,
  args       jsonb NOT NULL DEFAULT '{}',
  issued_by  uuid REFERENCES users(id),
  issued_at  timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  result     text, detail text, acked_at timestamptz
);
