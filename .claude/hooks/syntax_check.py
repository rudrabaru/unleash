import sys, json, subprocess

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

# Claude Code sends the target as tool_input.file_path for Edit/Write/MultiEdit;
# fall back to "path" for other IDE bridges.
tool_input = data.get("tool_input", {})
path = tool_input.get("file_path") or tool_input.get("path") or ""

if not path.endswith(".py"):
    sys.exit(0)

result = subprocess.run(
    [sys.executable, "-m", "py_compile", path],
    capture_output=True, text=True
)

if result.returncode != 0:
    sys.stderr.write(
        f"[syntax-check] WARNING: Syntax error detected in {path}:\n"
        f"{result.stderr.strip()}\n"
        "Fix this before running pytest."
    )

# PostToolUse cannot block — always exit 0, but stderr message is
# surfaced in Claude's context so it can self-correct immediately.
sys.exit(0)
