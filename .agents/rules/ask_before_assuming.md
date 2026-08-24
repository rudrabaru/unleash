# Rule: Ask Before Assuming

This rule applies unconditionally in every session, before any code is written or any file is modified.

## The Rule

**If there is ANY ambiguity, underspecification, or gap in the user's request, STOP and ask the user directly. Do not make assumptions to fill the gap. Do not proceed until the question is answered.**

This includes:
- Ambiguous filenames, function names, or module targets
- Unclear scope ("fix this" — which file? which bug?)
- Design decisions with multiple valid approaches (e.g., "add error handling" — which strategy?)
- Anything that requires choosing between two interpretations of a requirement
- Any action that would touch a file or path that wasn't explicitly mentioned

## What to Ask

Ask in a single, consolidated message. Do not ask one question, wait for an answer, then ask another — gather all open questions first, ask them together, then wait for all answers before writing any code.

## What Counts as "Assuming"

- Choosing an implementation approach without confirming it
- Inferring which file to edit from context clues alone when the user didn't specify
- Treating a vague instruction as a specific one (e.g., treating "add logging" as "add print statements")
- Extending scope beyond what was explicitly requested ("while I'm here, I'll also fix...")
- Deciding a clarification "isn't necessary" because the answer seems obvious

## What Does NOT Require Asking

- Mechanical tasks with no design decision (e.g., "run pytest", "show me the file", "add a docstring")
- Cases where only one implementation is plausible given the context in CLAUDE.md and the stage specs
- Follow-up to a plan the user has already explicitly approved
