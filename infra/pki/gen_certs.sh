#!/usr/bin/env bash
# Creates the local CA and the broker certificate (once), then one client certificate per device id.
# The CN of a client certificate is the MQTT user, so it must match the node id: node-0001, backend, ...
#
#   cd infra/pki
#   ./gen_certs.sh backend node-0001      # first run: CA + broker + two clients
#   ./gen_certs.sh node-0002              # later: only the new client; nothing already issued is replaced
#
# Output (git-ignored): ca.crt/ca.key, broker.crt/broker.key, <id>.crt/<id>.key in the current directory.
# BROKER_SAN overrides the names the broker certificate is valid for.
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash would otherwise rewrite the "/C=CO/..." subjects as file paths

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <device_id> [<device_id> ...]   e.g. $0 backend node-0001" >&2
    exit 1
fi

BROKER_SAN=${BROKER_SAN:-"DNS:localhost,DNS:mosquitto,DNS:gateway.local,IP:127.0.0.1"}

if [ ! -f ca.key ]; then
    openssl genrsa -out ca.key 2048
    openssl req -new -x509 -key ca.key -out ca.crt -days 3650 -subj "/C=CO/ST=Antioquia/O=SmartHive/CN=SmartHive-RootCA"
fi

if [ ! -f broker.key ]; then
    openssl genrsa -out broker.key 2048
    openssl req -new -key broker.key -out broker.csr -subj "/C=CO/O=SmartHive/CN=SmartHive-Broker"
    # Python and OpenSSL 3 check the name against subjectAltName, not the CN, so it has to be there
    printf "subjectAltName=%s\nextendedKeyUsage=serverAuth\n" "$BROKER_SAN" > broker.ext
    openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out broker.crt -days 365 -extfile broker.ext
    rm -f broker.ext
fi

for id in "$@"; do
    openssl genrsa -out "$id.key" 2048
    openssl req -new -key "$id.key" -out "$id.csr" -subj "/C=CO/O=SmartHive/CN=$id"
    printf "extendedKeyUsage=clientAuth\n" > "$id.ext"
    openssl x509 -req -in "$id.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "$id.crt" -days 365 -extfile "$id.ext"
    rm -f "$id.ext"
done
