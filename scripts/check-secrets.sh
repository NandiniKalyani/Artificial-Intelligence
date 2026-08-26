#!/usr/bin/env bash
# Blocks credentials from reaching a commit.
# Runs as a pre-commit hook. Also run it manually before a push.
#
#   ./scripts/check-secrets.sh           scan tracked files
#   ./scripts/check-secrets.sh --staged  scan staged changes only

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

if [ "${1:-}" = "--staged" ]; then
	FILES=$(git diff --cached --name-only --diff-filter=ACM)
else
	FILES=$(git ls-files)
fi

FILES=$(echo "$FILES" | grep -vE '^(_private/|scripts/check-secrets\.sh)' || true)
[ -z "$FILES" ] && { echo "nothing to scan"; exit 0; }

FAIL=0
report() { echo; echo "BLOCKED: $1"; echo "$2"; FAIL=1; }

# files that must never be committed at all
BADFILES=$(echo "$FILES" | grep -iE '(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|credentials\.json|service-account.*\.json|kubeconfig|.*\.kubeconfig|id_rsa|id_ed25519)$' | grep -v '\.env\.example$' || true)
[ -n "$BADFILES" ] && report "credential file staged" "$BADFILES"

# high confidence key formats
declare -a PATTERNS=(
	'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}'          # AWS access key
	'ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}'  # GitHub token
	'sk-[A-Za-z0-9]{32,}'                          # OpenAI style
	'xox[baprs]-[A-Za-z0-9-]{10,}'                 # Slack
	'-----BEGIN [A-Z ]*PRIVATE KEY-----'           # private key block
	'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}' # JWT
)
for p in "${PATTERNS[@]}"; do
	HITS=$(echo "$FILES" | xargs grep -nHE "$p" 2>/dev/null || true)
	[ -n "$HITS" ] && report "key or token pattern" "$HITS"
done

# assigned secrets with a real looking value, ignoring obvious placeholders
HITS=$(echo "$FILES" | xargs grep -nHiE '(password|passwd|secret|api_?key|token|access_?key)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{8,}' 2>/dev/null \
	| grep -viE '(example|placeholder|changeme|your[-_]|xxx|\.\.\.|<[a-z_]+>|\$\{|os\.getenv|getenv|environ|dummy|fake|test123|redacted)' || true)
[ -n "$HITS" ] && report "hardcoded secret value" "$HITS"

# private IPs and internal hostnames leak org detail
HITS=$(echo "$FILES" | grep -vE '\.(md)$' | xargs grep -nHE '\b(10\.[0-9]{1,3}|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b' 2>/dev/null || true)
if [ -n "$HITS" ]; then
	echo
	echo "WARN: private IP address. Fine if it is a docker network, check it is not internal."
	echo "$HITS"
fi

if [ "$FAIL" -eq 0 ]; then
	echo "secret scan passed"
else
	echo
	echo "Commit blocked. If a secret was already committed, rotate it first."
	echo "Removing it from the next commit does not remove it from history."
fi
exit "$FAIL"
