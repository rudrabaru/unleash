# Rule: Document Important Observations in Plain English

## Context
During the implementation of the Unleash Audio Pipeline (and subsequent pipeline stages), every major implementation must be accompanied by plain English documentation of all important observations, technical learnings, edge cases, and performance insights.

## Requirements
1. **Target Documentation**:
   - Update `docs/audio_pipeline_observations.md` with structured, plain English explanations after every major module implementation.
   - Update `docs/worklog.md` with the daily milestone progress.
   - Keep prototype notes (`backend/prototypes/NOTES.md`) updated when prototype findings translate to production code.
2. **Writing Style**:
   - Write in plain, direct English focusing on the *why*, the *risk*, and the *solution*.
   - Avoid overly dense or vague jargon; explain the practical impact of decisions.
3. **Trigger**:
   - After completing each pipeline stage (Stage 1 VAD, Stage 2 STT & phrase matching, Stage 3 voice authenticity, Stage 4 AV alignment, and fusion integration), document all findings before declaring the milestone complete.
