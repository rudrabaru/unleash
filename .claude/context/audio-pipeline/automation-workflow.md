# Audio Pipeline — Automation Workflow & Effective Prompting

This document captures how development-lifecycle automation is layered for the audio pipeline vertical, and how to prompt Claude Code so the right command gets invoked reliably. Read this once at the start of the project, and again any time a new automation layer (hooks, additional CI jobs) gets added.

---

## The Four-Layer Automation Model

| Layer | What it is | What it's for | Trigger |
|---|---|---|---|
| **CI (GitHub Actions)** | Deterministic, non-LLM, `.github/workflows/ci.yml` | Objective pass/fail: does it install, does pytest pass, do audio deps import cleanly | Automatic on `git push` / PR |
| **Slash commands** | LLM judgment, `.claude/commands/*.md` | "Is this really done," "is this schema-compliant," "was this scenario reported honestly" — anything a deterministic script can't decide | Only when explicitly typed (`/command-name`) |
| **Git / Claude Code hooks** | Not yet built in this repo — a future option (local `pre-commit`, or `PreToolUse` hooks in `.claude/settings.json`) | A fast local sanity net that fires even from a raw terminal, outside a Claude Code session | Automatic on the bound event, once configured |
| **Human approval** | You | The actual authorization for every commit/push/PR — nothing above substitutes for it | Explicit, every time |

**On "auto-triggered agents":** there is no mechanism where a well-written `description:` field makes a slash command or subagent fire on an event by itself. Reliable event-driven triggering only exists at the CI and hooks layers. If something genuinely needs to happen automatically on every push, it belongs in `ci.yml` (or a future hook) — not in a more elaborately-worded command description. Slash commands exist to be *reliably invokable on request*, not self-triggering; Section 3 below covers how to make that request reliable.

---

## Phase-Gate Workflow — Worked Example: "Finishing a Stage"

1. **Implement** the stage's real code.
2. **Local test:** `pytest backend/tests -v`, plus a manual run against real recordings.
3. **Slash-command checks**, in order: `/schema-check`, `/graceful-failure-audit "<stage>"`, `/stage-done "<stage>"` (and `/latency-benchmark` near Phase 2/3 milestones).
4. **Human review** of the check output — decide fix-and-loop-to-step-1, or proceed.
5. **Human-approved commit** — Claude drafts a specific message and stages the specific changed files (never `git add -A`); commits only after you explicitly say to.
6. **Push** to `feature/audio-pipeline` — again only on your explicit go-ahead.
7. **CI runs automatically** — check the actual result (`gh run list` / `gh run view`), don't assume green.
8. **If CI fails:** fix locally, re-run steps 2–3, create a **new** commit (never amend an already-pushed commit unless you explicitly ask) — never leave a known-broken commit at the branch tip.
9. **At milestone days only** (Day 8 / 22 / 30 / 40): open a PR from `feature/audio-pipeline` into `integration`. Re-run `/stage-done` against the full merge-ready scope and paste its verdict into the PR description as evidence. Merge only on your explicit instruction.

---

## Effective Prompting

The reliable contract is **typing the literal `/command-name`**. Prose requests work reasonably well too, but treat the slash command as the dependable path and prose as best-effort.

| Bad (ambiguous) | Good (names the command, scope, and boundary) |
|---|---|
| "check if the audio stuff is good" | "I just finished Stage 2 digit matching. Run `/schema-check backend/app/modules/audio`, then `/stage-done Stage 2`. Report only — don't fix anything yet." |
| "is this ready for Dev 3?" | "It's Day 22, handing off Stages 1–3. Run `/stage-done` (full module) and `/latency-benchmark` for Stages 1–3 combined. Give me a verdict before I open the integration PR." |
| "run the tests" | "Run `pytest backend/tests -v`, then `/scenario-runner 4 backend/tests/fixtures/scenario_4/` and `/scenario-runner 9 backend/tests/fixtures/scenario_9/`." |
| "tune the thresholds" | "Run `/threshold-sweep 'Stage 1 speech_duration' '1.5 to 2.5 step 0.25'` using the CSV from last week's scenario runs. Don't touch `stage-specifications.md` yet." |

### Reusable session-opening template

```
Day/Phase: Day <N>, Phase <P>.
Context check: confirm you've read root CLAUDE.md and .claude/context/audio-pipeline/ before we start.
Where I left off: <paste last /session-worklog entry, or check docs/worklog.md>.
Today's specific goal: <one concrete deliverable>.
Boundaries: don't touch Dev 2/Dev 3 module folders; report-only on all checks unless I say fix;
  never commit/push without my go-ahead.
```

Naming the phase/day lets Claude pick checklist items and commands appropriate to that point in the roadmap rather than guessing; one concrete goal creates a natural point to invoke the matching command; restating the two standing boundaries (ownership map, human-gated git) keeps them from relying on being "remembered" from `CLAUDE.md` alone every session.
