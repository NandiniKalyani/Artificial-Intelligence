#!/usr/bin/env bash
# Waits until every service can actually do its job, not just until the port
# opens. Use before anything that talks to the stack.
#
#   ./scripts/wait-for-stack.sh [seconds]   default 3600, the first model pull is slow

set -uo pipefail

DEADLINE=$(( $(date +%s) + ${1:-3600} ))
QDRANT="http://localhost:${QDRANT_HTTP_PORT:-6333}"
LOCALAI="http://localhost:${LOCALAI_PORT:-8081}"

waiting_for() {
	printf '%s ' "$1"
}

while :; do
	if [ "$(date +%s)" -gt "$DEADLINE" ]; then
		echo
		echo "gave up waiting. check: docker compose -f deploy/compose/docker-compose.yml logs"
		exit 1
	fi

	if ! curl -sf -m 5 "$QDRANT/readyz" >/dev/null 2>&1; then
		waiting_for qdrant
		sleep 5
		continue
	fi

	# a real generation, because the model answers /v1/models long before it can
	# answer a question
	if curl -sf -m 180 "$LOCALAI/v1/chat/completions" \
		-H 'Content-Type: application/json' \
		-d '{"model":"phi-3.5-mini","messages":[{"role":"user","content":"ok"}],"max_tokens":1}' \
		| grep -q choices; then
		echo
		echo "stack ready"
		exit 0
	fi

	waiting_for localai
	sleep 15
done
