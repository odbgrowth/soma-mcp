#!/usr/bin/env sh
# Run the official MCP conformance suite against a running SOMA MCP server.
#
#   MCP_SINGLE_USER=1 soma-mcp &          # local, unauthenticated, loopback
#   tools/run_conformance.sh http://127.0.0.1:8000/mcp
#
# Only the scenarios that apply to SOMA (its content is tools only) run; the
# others need fixture tools, resources or prompts SOMA deliberately does not
# have. The suites come from tools/conformance/package-lock.json (every
# transitive package pinned with an integrity hash, installed without install
# scripts): 0.1.x is the stable suite (handshake era); the 0.2.0 alpha is the
# first release with 2026-07-28 scenarios. Change versions in package.json and
# regenerate the lockfile with `npm install --package-lock-only --ignore-scripts`.
set -eu

URL="${1:-http://127.0.0.1:8000/mcp}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SUITES="$HERE/conformance"
BASELINE="$HERE/../.github/conformance-baseline.yml"

npm ci --prefix "$SUITES" --ignore-scripts --no-audit --no-fund
STABLE="$SUITES/node_modules/conformance-stable/dist/index.js"
MODERN="$SUITES/node_modules/conformance-modern/dist/index.js"

for scenario in server-initialize tools-list ping dns-rebinding-protection; do
  node "$STABLE" server --url "$URL" --scenario "$scenario"
done

for version in 2025-11-25 2026-07-28; do
  node "$MODERN" server --url "$URL" --scenario tools-list --spec-version "$version"
done

node "$MODERN" server --url "$URL" --scenario server-stateless \
  --spec-version 2026-07-28 --expected-failures "$BASELINE"
