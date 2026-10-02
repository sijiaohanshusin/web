#!/usr/bin/env bash
# Resolve main or accept an explicit SHA; never use a cached branch archive.
set -euo pipefail
sha=${1:-}
if [[ -z "$sha" ]]; then
    sha=$(curl -fsS --connect-timeout 10 --max-time 30 --retry 2 "https://api.github.com/repos/${HEUESTA_GH_REPO:-sijiaohanshusin/web}/commits/main" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
fi
exec bash "$(dirname "$(readlink -f "$0")")/release.sh" "$sha"
