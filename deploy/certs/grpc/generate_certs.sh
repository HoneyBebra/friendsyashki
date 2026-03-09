#!/usr/bin/env bash
# Generate self-signed TLS certificates for inter-service gRPC communication.
# Usage: ./generate_certs.sh
#
# Creates:
#   ca.pem          - CA certificate (shared by server and client)
#   server.key      - gRPC server private key  (auth service)
#   server.pem      - gRPC server certificate   (auth service)
#   client.key      - gRPC client private key  (messenger service)
#   client.pem      - gRPC client certificate   (messenger service)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DAYS=3650
SUBJ_CA="/CN=friendsyashki-grpc-ca"
SUBJ_SERVER="/CN=auth"
SUBJ_CLIENT="/CN=messenger"

echo "==> Generating CA key and certificate..."
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ca.key -out ca.pem \
  -days "$DAYS" -subj "$SUBJ_CA" 2>/dev/null

echo "==> Generating server key and CSR..."
openssl req -newkey rsa:4096 -nodes \
  -keyout server.key -out server.csr \
  -subj "$SUBJ_SERVER" 2>/dev/null

# SAN: allow connection by hostname "auth" (Docker service name) and localhost
cat > server_ext.cnf <<EOF
subjectAltName = DNS:auth, DNS:localhost, IP:127.0.0.1
EOF

echo "==> Signing server certificate with CA..."
openssl x509 -req -in server.csr \
  -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out server.pem -days "$DAYS" \
  -extfile server_ext.cnf 2>/dev/null

# Set restrictive permissions on private keys
chmod 600 server.key ca.key

echo "==> Generating client key and CSR..."
openssl req -newkey rsa:4096 -nodes \
  -keyout client.key -out client.csr \
  -subj "$SUBJ_CLIENT" 2>/dev/null

echo "==> Signing client certificate with CA..."
openssl x509 -req -in client.csr \
  -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out client.pem -days "$DAYS" 2>/dev/null

chmod 600 client.key

# Cleanup temporary files
rm -f server.csr server_ext.cnf client.csr ca.srl

echo "==> Done! Generated files:"
echo "    ca.pem      - CA certificate (mount to both services)"
echo "    ca.key      - CA private key (keep safe, needed for cert rotation)"
echo "    server.key  - Server private key (mount to auth only)"
echo "    server.pem  - Server certificate (mount to auth only)"
echo "    client.key  - Client private key (mount to messenger only)"
echo "    client.pem  - Client certificate (mount to messenger only)"
