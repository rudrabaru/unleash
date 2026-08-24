import sys, json, subprocess

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = data.get("tool_input", {}).get("path", "")

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
