#!/usr/bin/env bash
# Catches the writing tells listed in _private/process/writing-style.md
# Run before every push. Also wired in as a pre-commit hook.
#
#   ./scripts/check-style.sh          check tracked files
#   ./scripts/check-style.sh --staged check only what is staged

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

if [ "${1:-}" = "--staged" ]; then
	FILES=$(git diff --cached --name-only --diff-filter=ACM)
else
	FILES=$(git ls-files)
fi

# this script quotes the bad patterns on purpose, so skip it and the local notes
EXEMPT='^(_private/|scripts/check-style\.sh|CLAUDE\.md)'
FILES=$(echo "$FILES" | grep -vE "$EXEMPT" | grep -E '\.(md|py|yml|yaml|html|js|txt)$' || true)

[ -z "$FILES" ] && { echo "nothing to check"; exit 0; }

FAIL=0

# em dash U+2014, en dash U+2013
EM=$(printf '\xe2\x80\x94')
EN=$(printf '\xe2\x80\x93')

HITS=$(echo "$FILES" | xargs grep -nH -e "$EM" -e "$EN" 2>/dev/null || true)
if [ -n "$HITS" ]; then
	echo "FAIL: em dash or en dash found. Use a comma, colon, or full stop."
	echo "$HITS"
	FAIL=1
fi

# vocabulary that reads as machine written
WORDS='delve|leverag(e|ing)|robust|seamless|comprehensive|utiliz(e|ing)|foster|realm|landscape|testament|crucial|pivotal|moreover|furthermore|it.s worth noting|in conclusion|dive in'
HITS=$(echo "$FILES" | xargs grep -nHiE "\b($WORDS)\b" 2>/dev/null || true)
if [ -n "$HITS" ]; then
	echo
	echo "WARN: language model vocabulary. Rewrite unless it genuinely fits."
	echo "$HITS"
fi

# emoji in markdown headings
HITS=$(echo "$FILES" | grep '\.md$' | xargs grep -nHP '^#{1,6} .*[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]' 2>/dev/null || true)
if [ -n "$HITS" ]; then
	echo
	echo "FAIL: emoji in a heading."
	echo "$HITS"
	FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
	echo "style check passed"
fi
exit "$FAIL"
