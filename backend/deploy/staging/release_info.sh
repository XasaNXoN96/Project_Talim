#!/usr/bin/env bash
# Facts that identify a release candidate, for the operator's record (nothing secret: hashes, names, counts). Run from a clean checkout of the candidate:
#   backend/deploy/staging/release_info.sh
# It refuses to call a dirty tree a release candidate. It does not run the tests (see docs/RELEASE_CANDIDATE.md for the exact commands).
set -euo pipefail
cd "$(dirname "$0")/../../.."
if [ -n "$(git status --porcelain)" ]; then echo "NOT A RELEASE CANDIDATE: the working tree has uncommitted changes" >&2; exit 1; fi
echo "commit:        $(git rev-parse HEAD)"
echo "branch:        $(git rev-parse --abbrev-ref HEAD)"
echo "committed:     $(git log -1 --format=%cI)"
echo "requirements:  $(sha256sum backend/requirements.txt | cut -d' ' -f1)  (backend/requirements.txt, installed with --require-hashes)"
echo "migrations:    $(find backend/apps -path '*/migrations/0*.py' | wc -l) files; newest per app:"
for app in $(find backend/apps -type d -name migrations | sort); do
  latest="$(ls "$app" | grep -E '^0[0-9]+_.*\.py$' | sort | tail -n 1 || true)"
  [ -z "$latest" ] || printf '    %-14s %s\n' "$(basename "$(dirname "$app")")" "$latest"
done
echo "deploy files:  $(find backend/deploy -type f | wc -l) files; combined sha256 $(find backend/deploy -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)"
echo "static site:   $(git ls-files -- '*.html' 'assets' ':!backend' ':!docs' | xargs sha256sum | sha256sum | cut -d' ' -f1)  (repository-root pages and assets, must not change between candidates)"
