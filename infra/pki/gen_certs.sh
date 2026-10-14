#!/bin/bash

DEVICE_ID=$1

if [ -z "$DEVICE_ID" ]; then
    echo "Error: debes pasar el ID del dispositivo"
    echo "Uso: ./gen_certs.sh hive_01"
    exit 1
fi

#Generate a CA key
openssl genrsa -out ca.key 2048

#Generate a CA certificate
openssl req -new -x509 -key ca.key -out ca.crt -days 3650 -subj "//C=CO\ST=Antioquia\O=SmartHive\CN=SmartHive-RootCA"

#Generate a broker key
openssl genrsa -out broker.key 2048

#Generate a broker certificate signing request (CSR)
openssl req -new -key broker.key -out broker.csr -subj "//CN=smarthive-broker\O=SmartHive\C=CO"  

#Sign the broker CSR with the CA certificate to generate the broker certificate
openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out broker.crt -days 365

#Generate a hive key
openssl genrsa -out "$DEVICE_ID.key" 2048

#Generate a hive certificate signing request (CSR)
openssl req -new -key "$DEVICE_ID.key" -out "$DEVICE_ID.csr" -subj "//CN=$DEVICE_ID\O=SmartHive\C=CO"

#Sign the hive CSR with the CA certificate to generate the hive certificate
openssl x509 -req -in "$DEVICE_ID.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "$DEVICE_ID.crt" -days 365