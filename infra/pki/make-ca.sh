#!/usr/bin/env bash
# Local CA and the broker's server certificate. Run once; output goes to infra/pki/out (git-ignored).
# Copy out/ca.crt to every node. Keys never leave this machine.
set -euo pipefail
cd "$(dirname "$0")"
OUT=out
HOSTS="${SMARTHIVE_HOSTS:-gateway.local,localhost,mosquitto}"
mkdir -p "$OUT"
[ -f "$OUT/ca.key" ] && { echo "CA already exists in $OUT; delete it to start over" >&2; exit 1; }

# MSYS_NO_PATHCONV: keep Git Bash on Windows from rewriting the /CN= subject
export MSYS_NO_PATHCONV=1
openssl genrsa -out "$OUT/ca.key" 4096
openssl req -x509 -new -key "$OUT/ca.key" -sha256 -days 3650 -subj "/CN=SmartHive local CA" -out "$OUT/ca.crt"

openssl genrsa -out "$OUT/server.key" 2048
san=$(echo "$HOSTS" | tr ',' '\n' | awk '{printf "%sDNS:%s", (NR>1?",":""), $0}')
openssl req -new -key "$OUT/server.key" -subj "/CN=${HOSTS%%,*}" -out "$OUT/server.csr"
printf "subjectAltName=%s\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n" "$san" > "$OUT/server.ext"
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial -sha256 -days 825 \
  -extfile "$OUT/server.ext" -out "$OUT/server.crt"
rm -f "$OUT/server.csr" "$OUT/server.ext" "$OUT/ca.srl"
# the broker container runs as a different uid and only needs to read the key
chmod 600 "$OUT/ca.key"; chmod 644 "$OUT/server.key" "$OUT/server.crt" "$OUT/ca.crt"
openssl verify -CAfile "$OUT/ca.crt" "$OUT/server.crt"
echo "Install $OUT/ca.crt on each node. Broker listens on 8883 only."
