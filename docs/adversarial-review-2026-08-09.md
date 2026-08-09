# Adversarial review — gauntletx v0.2.4

Findings from studying the Gauntlet Loop method and a full worked implementation of it
(`mshumer/Claude-of-Duty`) against what gauntletx actually emits.

**Status: PROPOSAL. No change made to `SYSTEM_PROMPT` or any live code.** The prompt is
visibly tuned and every word in it is load-bearing; the diffs below are for review, not
application. Companion reference: [visual-gauntlet-loop.md](visual-gauntlet-loop.md).

Date: 2026-08-09 · reviewed against `gauntletx.py` at v0.2.4

---

## What holds up

The central claim is correct and is the thing comparable tools miss:

> the prompt does not describe the product — it describes who is allowed to call it finished

Also genuinely right, and worth not breaking:

- Rejecting "make it amazing" / "production-ready" as bars outright.
- Refusing to prescribe architecture — *"Give the destination, let the agent choose the route."* Claude-of-Duty's 941-byte prompt specified no file layout and the agent produced a clean subsystem split with an ownership map. Prescribing it would have made that worse.
- Per-harness closers, with the `(web)` degradation path handled honestly.
- The amber chat-adaptation warning ([gauntletx.py:1291](../gauntletx.py#L1291)). This is the strongest UX idea in the product: **detect a capability mismatch, tell the user the method will be weaker.** Three findings below are solved by extending exactly this pattern.

---

## Finding 1 — Inspection is required; the *means* of inspection is not

`SYSTEM_PROMPT` part 2 ([gauntletx.py:123](../gauntletx.py#L123)) requires the critic to
inspect "the ACTUAL artifact … never the builder's summary."

Nothing instructs the agent to **build the thing that produces that artifact.**

Claude-of-Duty did not succeed because it was told to look at pixels. It succeeded because
it built `tools/capture.mjs` — Playwright, headless GPU Chromium, a `window.__READY__` boot
gate, named fixed camera shots, and **90 settle frames** so temporal antialiasing had
converged before the frame was judged — and then made it a hard gate:

> `npm run build` must pass and `node tools/capture.mjs` must produce a frame after your
> change. **If you break the boot, nobody else can work.**

**Why this is severe:** the failure is silent. Without a harness, "inspect the real pixels"
degrades into an agent reading source and asserting quality. The loop still runs, still
reports rounds, still claims improvement. Nothing in the transcript looks wrong.

This generalises to every work type — the harness is just whatever regenerates the
judged artifact deterministically:

| Work type | Inspection harness |
|---|---|
| Game | headless screenshot, fixed camera, settle frames |
| Website or app | rendered page, fixed viewport, fixed fixtures |
| Backend or code | the test / benchmark command, fixed seed and dataset |
| Writing | the rendered final text, not a diff |
| Design | the exported asset |
| Research | the claim-check procedure |
| Challenge | the scoring command (see Finding 3) |

## Finding 2 — The bar preference maximises Goodhart risk

[gauntletx.py:102](../gauntletx.py#L102) prefers a machine-checkable bar: "a named test
suite that must pass, a benchmark number that must move, a latency target."

Combine three properties the tool already has:

1. a measurable target,
2. no fixed round count (*"until ours wins or I stop the run"*),
3. a critic whose sole job is closing the gap to that number.

That is a Goodhart engine. Forty rounds against a test suite produces special-cased tests;
against a latency target, a cached benchmark input.

**Claude-of-Duty is safe from this by accident** — an agent cannot game "looks better than
Call of Duty" because it cannot ship a new Call of Duty. Generalising to measurable bars
removes that accidental protection, so the protection now has to be explicit.

Note this cuts against a stated principle rather than an oversight. The preference for
machine-checkable bars is right; it just needs the counterweight.

## Finding 3 — Only one loop shape exists, and "challenges" need the other

Every current `WORK_TYPE` — Game, Website or app, Writing, Backend or code, Design,
Marketing, Research — is an **artifact-production** category, and the three-part prompt
encodes one loop:

```
build → critique → rebuild
```

A challenge is a different shape:

```
attempt → score → diagnose → re-attempt
```

Beat a benchmark, solve the problem, find the bug, get the model above X. There is no blind
side-by-side, because there is nothing to compare aesthetically — there is a **score**.

That loop needs three things the current prompt never emits:

| Need | Why |
|---|---|
| A scoring harness | The equivalent of `capture.mjs` — one command returning a number |
| A held-out set | Attempt loops overfit faster than build loops (Finding 2) |
| Best-so-far tracking | Attempts go backwards; without a champion record a run can end below its own peak |

And the critic's role inverts: from *"which of these is better"* to *"why did this attempt
score what it scored, and what is the highest-value next change."* Diagnosis, not
comparison.

---

## Proposed diffs

Three changes, written to be pasted. Anchors are exact as of v0.2.4.

### Diff 1 — require the inspection harness

`SYSTEM_PROMPT`, part 2. After the existing sentence ending
*"…sends it back to the builder for another round."* ([gauntletx.py:126](../gauntletx.py#L126)):

```diff
    text) — never the builder's summary — and if it does not meet the bar, it names the
    single biggest remaining gap and sends it back to the builder for another round.
+   Tell the agent, in one clause, to stand up the inspection harness before the first
+   critic round — the single command that regenerates the judged artifact identically
+   every round — and to keep that command working as a gate on every later change. Say
+   what it must produce, never how to build it. Without it "inspect the real artifact"
+   silently becomes the agent reading its own source.
```

### Diff 2 — held-out check on machine-checkable bars

`SYSTEM_PROMPT`, THE BAR. Insert after the MACHINE-CHECKABLE bullet
([gauntletx.py:102-106](../gauntletx.py#L102)):

```diff
   a machine cannot score (visuals, prose, feel). Remember: the prompt does not describe
   the product — it describes who is allowed to call it finished.
+- A machine-checkable bar is also the easiest to game, and an unbounded loop will game it:
+  special-cased tests, a cached benchmark input, a metric moved without the underlying
+  work. Whenever the bar is machine-checkable, name something held back from the builder
+  as part of the bar — a reserved test set, an unseen input distribution, or the same
+  quantity measured a second way — and state that a round which moves the headline number
+  while failing the held-out check is a failed round.
```

### Diff 3 — `Challenge or benchmark` work type

**3a.** `WORK_TYPES` ([gauntletx.py:299](../gauntletx.py#L299)):

```diff
-WORK_TYPES = ("Auto", "Game", "Website or app", "Writing", "Backend or code",
-              "Design", "Marketing", "Research", "Other")
+WORK_TYPES = ("Auto", "Game", "Website or app", "Writing", "Backend or code",
+              "Design", "Marketing", "Research", "Challenge or benchmark", "Other")
```

**3b.** `DRAFT_PROMPT` field rules ([gauntletx.py:242](../gauntletx.py#L242)):

```diff
-- WORK_TYPE: exactly one of: Auto, Game, Website or app, Writing, Backend or code,
-  Design, Marketing, Research, Other.
+- WORK_TYPE: exactly one of: Auto, Game, Website or app, Writing, Backend or code,
+  Design, Marketing, Research, Challenge or benchmark, Other. Use "Challenge or
+  benchmark" when success is a score, a pass/fail, or a target to beat rather than an
+  artifact to admire — solve this, beat this number, find the bug, win this competition.
```

**3c.** The form select ([gauntletx.py:1018-1020](../gauntletx.py#L1018)):

```diff
       <option>Writing</option><option>Backend or code</option><option>Design</option>
-      <option>Marketing</option><option>Research</option><option>Other</option></select></div>
+      <option>Marketing</option><option>Research</option>
+      <option>Challenge or benchmark</option><option>Other</option></select></div>
```

**3d.** `SYSTEM_PROMPT`, a new mode block beside POLISH MODE
([gauntletx.py:171](../gauntletx.py#L171)):

```diff
+CHALLENGE MODE: when the work type is "Challenge or benchmark", the loop is attempt →
+score → diagnose → re-attempt, not build → critique → rebuild. Part 2 instead tells the
+agent to stand up the scoring command first and score every attempt with it; the separate
+critic diagnoses why an attempt scored what it did and names the highest-value next
+change, rather than comparing two artifacts. Part 3's bar is the number to beat plus the
+held-out check, and it tells the agent to keep a best-so-far record and never report a
+result below its own peak. No blind side-by-side — a score replaces it.
```

---

## The cost of these diffs, stated honestly

`SYSTEM_PROMPT` ends with **"80–180 words total"** for the emitted prompt. Diffs 1 and 2
each add a required sentence to the output, roughly **20–30 words each**. Applied
unconditionally they push typical output toward the ceiling and risk crowding out the parts
that already work.

Two ways to pay for it, both worth deciding before shipping:

- **Make them conditional.** The harness sentence matters most where inspection is
  non-trivial (Game, Website, Design, Challenge) and least for Writing, where the artifact
  *is* the text. The held-out sentence only applies when the chosen bar is
  machine-checkable — which the model already decides.
- **Raise the ceiling to 200 words** for those work types only.

I would not apply either diff globally without testing the word count against the existing
smoke tests.

## Findings not in the top three

Recorded for completeness, roughly in order of value:

1. **"Blind" is asserted, not constructed.** One run, one agent lineage — the critic can usually infer which artifact is the new one. Fix is mechanical: present as A/B in randomised order, record the pick before revealing.
2. **No determinism requirement.** For an A/B to be valid, two rounds must differ *only* because of the change. Claude-of-Duty enforces seeded RNG, fixed shots, settle frames, no hot reload. Without it the critic grades variance and the loop can oscillate indefinitely — which, with no round cap, is an unbounded-spend failure mode.
3. **No cost framing anywhere.** The README says "paste that into your agent and walk away." A measured agentic session of this shape ran **1,779 requests / 183.6M tokens in 19.5 hours**. Shumer's own page is blunter: *"It costs much more."* Suggest a UI note by the harness picker plus a plateau clause — *"if two consecutive rounds close no gap the critic accepts, stop and report."* There is currently no exit except the user noticing.
4. **Modality mismatch on local targets.** `WORK_TYPE = Game` with a text-only local harness emits a prompt telling a text-only model to blind-compare two images. It will comply by reading code. Extend the line 1291 warning pattern.
5. **Reference *names* vs reference *pixels*.** Blind A/B needs artifacts on both sides; naming a product only works if the agent can obtain frames. For visual work types, supplied reference files should be required rather than optional.

## Suggested sequencing

1. Diff 3 first — additive, no effect on existing output, and it is the capability gap.
2. Diff 1 next, conditional by work type, with smoke tests on word count.
3. Diff 2 last — it changes bar selection, the most tuned part of the prompt.
