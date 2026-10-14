#!/usr/bin/env bash
# Acceptance check for US04 against a running stack (docker compose up first).
#   MQTT_BACKEND_PASSWORD=... MQTT_NODE1_PASSWORD=... bash infra/mosquitto/test_broker.sh
# node-0001 and the backend account must exist (infra/mosquitto/users.sh).
set -u  # no pipefail: grep -q closes the pipe early
export MSYS_NO_PATHCONV=1  # Git Bash on Windows would rewrite the /mosquitto/... paths
cd "$(dirname "$0")/.."
C="docker compose -f compose.yaml exec -T mosquitto"
TLS="-h localhost -p 8883 --cafile /mosquitto/certs/ca.crt"
fail=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }

# 1. nothing listens on 1883, inside the container or published to the LAN
$C timeout 4 mosquitto_pub -h localhost -p 1883 -t t -m x 2>&1 | grep -qi "refused" && ok "plain 1883 refused" || bad "plain 1883 accepted a connection"
(echo > /dev/tcp/127.0.0.1/1883) >/dev/null 2>&1 && bad "1883 reachable from the host" || ok "1883 not published on the host"

# 2. TLS without credentials is refused
$C timeout 4 mosquitto_pub $TLS -t t -m x 2>&1 | grep -qi "not authori" && ok "anonymous publish refused" || bad "anonymous publish not refused"

# 3. a node writes only its own topics: backend listens, node-0001 publishes to its topic and to node-0002's
out=$($C sh -c "mosquitto_sub $TLS -u backend -P '$MQTT_BACKEND_PASSWORD' -t 'smarthive/v1/nodes/+/health' -W 6 -C 2 2>/dev/null" &
  sleep 2
  $C mosquitto_pub $TLS -u node-0001 -P "$MQTT_NODE1_PASSWORD" -q 1 -t smarthive/v1/nodes/node-0002/health -m other-node
  $C mosquitto_pub $TLS -u node-0001 -P "$MQTT_NODE1_PASSWORD" -q 1 -t smarthive/v1/nodes/node-0001/health -m own-node
  wait)
echo "$out" | grep -q own-node && ok "node-0001 can publish to its own topic" || bad "own topic not delivered"
echo "$out" | grep -q other-node && bad "node-0001 published to node-0002's topic" || ok "cross-node publish denied by ACL"
exit $fail
