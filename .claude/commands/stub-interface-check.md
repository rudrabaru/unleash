---
description: Confirm the audio module's public entrypoint (name, params, return type) exactly matches what Dev 3's orchestrator actually calls — the most common Day-8/Day-22 handoff bug.
argument-hint: "[optional: path to the orchestrator/caller code to check against]"
allowed-tools: Read, Grep, Glob
---

You are running the **stub/interface handoff check** for the audio pipeline — the automation named in the Unleash agentic development guide (Part 4, Automation #4). A mismatched parameter name or return-shape between what Dev 1 exports and what Dev 3's orchestrator expects to call is one of the most common silent-breakage bugs at integration handoffs, precisely because it doesn't crash locally — it only fails when the other side wires it up.

## What to do

1. Read `backend/app/modules/audio/__init__.py` (or wherever the audio module's current public entrypoint lives — confirm by reading the actual file, not by assuming the name `process_audio_pipeline` is still current) and record: exact function name, whether it's `async`, parameter names/order/types, and return type.
2. Find every place in the codebase that calls into this function — search `backend/app/` broadly (the orchestrator may live under `backend/app/modules/antispoof/` per the ownership map in root `CLAUDE.md`, or still be the `mock_background_pipeline` stub in `backend/app/api/v1/endpoints/sessions.py` if Dev 3 hasn't built the real orchestrator yet). If `$ARGUMENTS` names a specific file, check that one specifically in addition to searching.
3. Compare: does the caller pass arguments in the name/order/type the producer actually expects? Does the caller do anything with the return value (e.g. treat it as a `DetectorResult`, access `.score`/`.passed`) that assumes a shape the producer doesn't actually provide?
4. If no real caller exists yet (only the `mock_background_pipeline` stub calling nothing real), say so explicitly — this check has nothing to verify yet, and that is a valid, honestly-reported outcome, not a failure to force.

## Output format

Report: (a) the producer's actual current signature, (b) every call site found and what it expects, (c) a PASS/FAIL/NOTHING-TO-CHECK-YET verdict with the specific mismatch quoted if FAIL. Do not rename or edit either side to "fix" a mismatch — report which side is stale and wait for direction, since the fix might belong to Dev 3's code, not yours.
