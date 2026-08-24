import sys, json

SCHEMA_FILES = [
    "backend/app/schemas/detector.py",
    "backend/app/schemas/",
]

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = data.get("tool_input", {}).get("path", "")
path = path.replace("\\", "/")

if any(s in path for s in SCHEMA_FILES):
    sys.stderr.write(
        "[schema-guard] BLOCKED: Attempted edit to the shared DetectorResult schema. "
        "Per CLAUDE.md Section G, changes to backend/app/schemas/ require explicit team discussion "
        "before any code is written. "
        "Report this block to the user and ask for explicit authorization before proceeding."
    )
    sys.exit(2)

sys.exit(0)
