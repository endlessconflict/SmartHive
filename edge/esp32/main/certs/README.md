# Device certificates

The build embeds three files from this folder when `SMARTHIVE_MQTT_TLS` is on. They are git-ignored.

```bash
cd infra/pki
./gen_certs.sh node-0001                       # once per node; the CN is the MQTT user
cp ca.crt        ../../edge/esp32/main/certs/ca.crt
cp node-0001.crt ../../edge/esp32/main/certs/node.crt
cp node-0001.key ../../edge/esp32/main/certs/node.key
```

The node id in `menuconfig` must be the same as the certificate CN, otherwise the broker ACL drops every message.
