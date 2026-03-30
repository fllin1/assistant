#!/usr/bin/env bash
# PostToolUse hook: runs ruff check --fix and ruff format on .py files after Write|Edit
file_path=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
p = d.get('tool_input', {}).get('file_path') or d.get('tool_response', {}).get('filePath', '')
print(p)
")

if echo "$file_path" | grep -qE '\.py$'; then
    ruff check --fix "$file_path" 2>/dev/null || true
    ruff format "$file_path" 2>/dev/null || true
fi
