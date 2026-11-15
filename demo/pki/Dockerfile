# One-shot: creates the CA, the broker certificate and one certificate per service and simulated node in the
# `pki` volume, the first time only. The same script as infra/pki, so the demo uses the real mTLS set-up.
FROM alpine:3.20
RUN apk add --no-cache bash openssl
COPY gen_certs.sh /usr/local/bin/gen_certs.sh
WORKDIR /pki
# Demo only: the keys are world-readable inside the volume so the broker (uid 1883) and the services can read them.
CMD ["sh", "-c", "[ -f ca.crt ] || { gen_certs.sh backend sim-0001 sim-0002 sim-0003 sim-0004 sim-0005 && chmod 644 *.key *.crt; }"]
