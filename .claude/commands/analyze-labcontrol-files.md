---
description: Read and summarize CLAUDE.md, BACKEND.md, DEPLOYMENT.md, and LABWIN_BACKUP_PIPELINE.md
argument-hint: (no args)
allowed-tools: Read, Bash
---

Analyze the four core LabControl reference docs and produce a concise briefing.

**Files to read** (always read all four, in parallel):
1. `/Users/cevichesmac/Desktop/labcontrol/CLAUDE.md` — AI context index, non-negotiable conventions, current status
2. `/Users/cevichesmac/Desktop/labcontrol/BACKEND.md` — full backend reference (large file, ~2,300 lines — read with offset/limit if it exceeds the token budget)
3. `/Users/cevichesmac/Desktop/labcontrol/DEPLOYMENT.md` — production runbook (Hostinger VPS, Docker Compose, nginx, SSL, FTP)
4. `/Users/cevichesmac/Desktop/labcontrol/LABWIN_BACKUP_PIPELINE.md` — LabWin backup ingestion design + current phase status

**What to produce** — one short section per file, plus a final cross-cutting section. Keep total output under ~600 words. For each file:

- **Purpose** in one sentence
- **3–6 bullets** of the most load-bearing facts: stack, key models / endpoints / services, conventions, gotchas, pending work
- File size (lines) and last-updated date if visible

**Cross-cutting section** — surface things that span multiple docs:
- Conventions that get violated most often (e.g. `.pk` vs `.id`)
- Items gated on the same external decision (e.g. lab signup workflow)
- Drift between docs (test counts, dates, status mismatches)
- Pending operational hygiene (secret rotation, schedule activation, etc.)

**Tone**: terse, factual, no filler. Assume the reader is the project owner — skip explaining what LabControl is. Lead with what changed or what's surprising, not the table of contents.

If any of the four files are missing, report which and proceed with the rest.
