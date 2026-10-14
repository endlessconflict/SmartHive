#!/usr/bin/env bash
# Add or update an MQTT user in infra/mosquitto/passwd (git-ignored).
#   users.sh node-0001            random password, printed once
#   users.sh backend 's3cret'     given password
# Uses the broker image, so no local Mosquitto install is needed.
set -euo pipefail
cd "$(dirname "$0")"
user=${1:?usage: users.sh <username> [password]}
pass=${2:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)}
touch passwd
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/c" eclipse-mosquitto:2.0.22 mosquitto_passwd -b /c/passwd "$user" "$pass"
echo "$user $pass"
