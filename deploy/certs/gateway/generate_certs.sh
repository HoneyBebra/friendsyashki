#!/usr/bin/env bash
# Generate self-signed TLS certificates for nginx gateway (HTTPS termination).
# Usage: ./generate_certs.sh
#
# Creates:
#   ca.pem          - CA certificate
#   server.key      - Server private key  (nginx gateway)
#   server.pem      - Server certificate   (nginx gateway)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DAYS=3650
SUBJ_CA="/CN=friendsyashki-gateway-ca"
SUBJ_SERVER="/CN=localhost"

echo "==> Generating CA key and certificate..."
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ca.key -out ca.pem \
  -days "$DAYS" -subj "$SUBJ_CA" 2>/dev/null

echo "==> Generating server key and CSR..."
openssl req -newkey rsa:4096 -nodes \
  -keyout server.key -out server.csr \
  -subj "$SUBJ_SERVER" 2>/dev/null

# SAN: allow connection by hostname "nginx_gateway" (Docker service name) and localhost
cat > server_ext.cnf <<EOF
subjectAltName = DNS:nginx_gateway, DNS:localhost, IP:127.0.0.1, IP:192.168.1.174
EOF

echo "==> Signing server certificate with CA..."
openssl x509 -req -in server.csr \
  -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out server.pem -days "$DAYS" \
  -extfile server_ext.cnf 2>/dev/null

# Set restrictive permissions on private keys
chmod 600 server.key ca.key

# Cleanup temporary files
rm -f server.csr server_ext.cnf ca.srl

echo "==> Done! Generated files:"
echo "    ca.pem      - CA certificate"
echo "    ca.key      - CA private key (keep safe, needed for cert rotation)"
echo "    server.key  - Server private key (mount to nginx gateway)"
echo "    server.pem  - Server certificate (mount to nginx gateway)"
