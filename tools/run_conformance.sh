#!/usr/bin/env sh
# Run the official MCP conformance suite against a running SOMA MCP server.
#
#   MCP_SINGLE_USER=1 soma-mcp &          # local, unauthenticated, loopback
#   tools/run_conformance.sh http://127.0.0.1:8000/mcp
#
# Only the scenarios that apply to SOMA's tools-only profile run; the others
# need fixture tools, resources or prompts that SOMA deliberately does not have.
# Versions are pinned: 0.1.x is the stable suite (handshake era); the 0.2.0
# alpha is the first release with 2026-07-28 scenarios.
set -eu

URL="${1:-http://127.0.0.1:8000/mcp}"
STABLE="@modelcontextprotocol/conformance@0.1.16"
MODERN="@modelcontextprotocol/conformance@0.2.0-alpha.12"
BASELINE="$(dirname "$0")/../.github/conformance-baseline.yml"

for scenario in server-initialize tools-list ping dns-rebinding-protection; do
  npx --yes "$STABLE" server --url "$URL" --scenario "$scenario"
done

for version in 2025-11-25 2026-07-28; do
  npx --yes "$MODERN" server --url "$URL" --scenario tools-list --spec-version "$version"
done

npx --yes "$MODERN" server --url "$URL" --scenario server-stateless \
  --spec-version 2026-07-28 --expected-failures "$BASELINE"
