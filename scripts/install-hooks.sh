#!/usr/bin/env bash
# Installs the pre-commit hook. Run once after cloning.
#   ./scripts/install-hooks.sh

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
# Blocks a commit if secrets or AI writing tells are present.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"

"$ROOT/scripts/check-secrets.sh" --staged || exit 1
"$ROOT/scripts/check-style.sh" --staged   || exit 1
HOOK

chmod +x .git/hooks/pre-commit
echo "pre-commit hook installed"
echo "it runs check-secrets.sh then check-style.sh on staged files"
echo
echo "to skip it in an emergency: git commit --no-verify"
echo "(do not make a habit of it)"
