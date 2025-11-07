#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="$SCRIPT_DIR/../certs"

echo "Generating self-signed SSL certificates for testing..."

# Create certs directory
mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

# Generate CA (Certificate Authority)
echo "1. Generating CA certificate..."
openssl genrsa -out ca.key 2048 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -out ca.crt \
    -subj "/C=US/ST=Test/L=Test/O=SceneScape Test CA/CN=Test CA" 2>/dev/null

# Generate server certificate for Mosquitto broker
echo "2. Generating server certificate for broker.scenescape.intel.com..."
openssl genrsa -out server.key 2048 2>/dev/null
openssl req -new -key server.key -out server.csr \
    -subj "/C=US/ST=Test/L=Test/O=SceneScape/CN=broker.scenescape.intel.com" 2>/dev/null

# Create SAN config for server cert
cat > server.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = broker.scenescape.intel.com
DNS.2 = mqtt-broker
DNS.3 = localhost
EOF

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 365 -sha256 -extfile server.ext 2>/dev/null

# Generate client certificate for tracker
echo "3. Generating client certificate for tracker-service..."
openssl genrsa -out client.key 2048 2>/dev/null
openssl req -new -key client.key -out client.csr \
    -subj "/C=US/ST=Test/L=Test/O=SceneScape/CN=tracker-service" 2>/dev/null
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out client.crt -days 365 -sha256 2>/dev/null

# Cleanup temp files
rm -f server.csr server.ext client.csr ca.srl

echo ""
echo "✓ Certificates generated successfully in $CERTS_DIR/"
echo "  - CA: ca.crt, ca.key"
echo "  - Server: server.crt, server.key"
echo "  - Client: client.crt, client.key"
echo ""
echo "Note: These are self-signed certificates for DEVELOPMENT ONLY."
echo "      Do NOT use in production environments."
