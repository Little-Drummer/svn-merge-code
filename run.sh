#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SKILL_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到虚拟环境 Python：$PYTHON" >&2
  echo "请先执行：python3 -m venv \"$SKILL_DIR/.venv\" && \"$SKILL_DIR/.venv/bin/python\" -m pip install -r \"$SKILL_DIR/requirements.txt\"" >&2
  exit 1
fi

exec "$PYTHON" "$SKILL_DIR/scripts/svn_merge.py" "$@"
