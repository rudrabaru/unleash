import sys, json

PROTECTED = [
    "backend/app/modules/visual/",
    "backend/app/modules/antispoof/",
    "backend/app/api/v1/endpoints/eval.py",   # Dev 3 only
]

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = data.get("tool_input", {}).get("path", "")
path = path.replace("\\", "/")

if any(p in path for p in PROTECTED):
    sys.stderr.write(
        f"[ownership-guard] BLOCKED: '{path}' belongs to another developer's exclusive module. "
        "Per CLAUDE.md Section C, never modify this path without an explicit cross-team request from the user. "
        "Report this block to the user and ask for a cross-team change instruction before proceeding."
    )
    sys.exit(2)

sys.exit(0)
