---
trigger: always_on
---

# Rule: Professional Commit Message Generation

## Purpose
Enforce a consistent, clear, and professional standard for summarizing working tree changes into Git commit messages after the implementation of any feature or fix.

## Constraints & Standards
1. **Plain English & Technical Precision**:
   - Focus on *what* was implemented logically and *why*.
   - Never use vague labels like "WIP", "various fixes" or project-internal numbering in commit headers or bullet points.
2. **Conventional Commit Format**:
   - Header: `<type>(<scope>): <concise active-voice description>`
   - Body: Bulleted summary detailing the concrete functional components, error handling, algorithms, and tests added or modified. (not more than 5 points)
3. **Diff-Grounded**:
   - Commit messages must be derived strictly from actual `git status` and `git diff` outputs, reflecting only what is physically staged or changed, instead of any code or file-level details.