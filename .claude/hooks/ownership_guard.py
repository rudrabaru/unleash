import sys, json

# Exclusive to another developer's vertical (CLAUDE.md Section C) or requiring
# team agreement before any edit (CLAUDE.md Section G).
PROTECTED = [
    "backend/app/modules/visual/",
    "backend/app/modules/antispoof/",
    "backend/app/api/v1/endpoints/eval.py",   # Dev 3 only
    "backend/app/core/",                       # shared — config + HMAC (Section G)
]
# Note: backend/app/api/v1/endpoints/sessions.py is split-owned (Dev 2 creation
# logic / Dev 3 orchestration). Not hard-blocked here, but Dev 1 should only
# touch it for an explicitly agreed cross-team change.

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

# Claude Code sends the target as tool_input.file_path for Edit/Write/MultiEdit;
# fall back to "path" for other IDE bridges.
tool_input = data.get("tool_input", {})
path = tool_input.get("file_path") or tool_input.get("path") or ""
path = path.replace("\\", "/")

if any(p in path for p in PROTECTED):
    sys.stderr.write(
        f"[ownership-guard] BLOCKED: '{path}' belongs to another developer's exclusive module. "
        "Per CLAUDE.md Section C, never modify this path without an explicit cross-team request from the user. "
        "Report this block to the user and ask for a cross-team change instruction before proceeding."
    )
    sys.exit(2)

sys.exit(0)
