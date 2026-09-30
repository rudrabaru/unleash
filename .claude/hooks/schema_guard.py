import sys, json

# The directory substring covers detector.py and every other shared schema file.
SCHEMA_FILES = [
    "backend/app/schemas/",
]

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

# Claude Code sends the target as tool_input.file_path for Edit/Write/MultiEdit;
# fall back to "path" for other IDE bridges.
tool_input = data.get("tool_input", {})
path = tool_input.get("file_path") or tool_input.get("path") or ""
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
