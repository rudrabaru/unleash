"""Ask for confirmation before any edit to the shared detector contract.

Every detector returns the `DetectorResult` defined in backend/app/schemas/detector.py.
Changing it changes what every module and the fusion engine can rely on, so the edit is
allowed only after the owner confirms it (the hook asks instead of blocking).
"""
import json
import sys

CONTRACT_FILE = "backend/app/schemas/detector.py"

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

# Claude Code sends the target as tool_input.file_path for Edit/Write/MultiEdit;
# fall back to "path" for other IDE bridges.
tool_input = data.get("tool_input", {})
path = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")

if path.endswith(CONTRACT_FILE):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "This file defines the detector result contract used by every module and by "
                "fusion. Confirm that the contract is meant to change, and log the decision in "
                ".claude/context/decisions.md."
            ),
        }
    }))

sys.exit(0)
