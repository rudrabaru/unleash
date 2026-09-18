import sys, json

# Exclusive to another developer's vertical (CLAUDE.md Section C) or requiring
# team agreement before any edit (CLAUDE.md Section G).
PROTECTED = [
    "backend/app/core/",                       # shared — config + HMAC (Section G)
]
# NOTE (temporary, cross-team authorized): visual/, antispoof/, eval.py and
# sessions.py were removed from this list because the user explicitly asked
# Dev 1 to implement all three verticals solo on feature/audio-pipeline (see
# conversation authorizing this under CLAUDE.md Section C's "explicit
# cross-team/pairing change" exception). core/ stays guarded since it's a
# Section G shared-agreement item, not a per-developer ownership boundary.

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
