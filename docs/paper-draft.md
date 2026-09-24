# The Runtime Is Not Infrastructure: A Replication of SKILL.state

**Draft.** Every figure comes from a measurement in this repository, with per-step
traces and raw data on the `runs/table1-gemini-3-flash-preview-vertex` branch.

---

## 1. What the paper claims, and what we measured

[SKILL.state](https://arxiv.org/abs/2608.26263) argues that an agent maintaining
**explicit state** executes long procedures far better than one carrying the whole
conversation, and that the gap widens with the horizon. Its Table 1 shows this with
Gemini-3-Flash in a simulated warehouse: ReAct falls from 0.90 to 0.74 between 10 and
200 steps while SKILL.state holds at 0.94.

We reimplemented their environment from the paper's description — SkillExecBench is not
public — and measured three things:

1. **Whether the ladder reproduces** under their own model and decoding settings (§3).
2. **What each runtime actually costs** when you count money rather than tokens (§4).
3. **What explicit state protects against**, through two probes aimed at the
   limitations the paper itself declares but does not measure (§5).

The short version: **their thesis holds, their magnitude does not, and their cost
accounting inverts once you bill it**. Explicit state protects against losing track of
the procedure; on a second model it does not protect against **writing the state
wrong**, and that failure — not the one the paper studies — is what ends up limiting it.
And the largest effects in the whole experiment come not from any of the compared
methods, but from runtime implementation decisions the paper treats as neutral: one of
them silently disabled one of our four arms for the whole project (§6).

---

## 2. Environment fidelity, and the differences we declare

The paper publishes the environment design (Appendix B.1), the generator pseudocode
(Algorithm 2) and the prompts (Appendix A), so the comparison is not blind.

**What matches**: 500 single-occupancy shelves, the action space
(`Store`/`Ship`/`Move`/`Wait`), item destruction on `Ship`, the metric (valid actions
executed / actionable events) and per-seed determinism.

**What did not match, and is now closed behind flags** (`--apendice-b`,
`--sin-telemetria`):

| Difference | What we did |
|---|---|
| No maintenance events, so `Move` was never exercised | Implemented: 11–20 per 50-step episode |
| Invalid actions were applied rather than rejected | Rejection with a local error observation, as in their B.1 |
| A third of our steps were non-actionable telemetry | Removed: their Algorithm 2 has no non-actionable family |

**Closing all three produces no detectable change.** ReAct at T=200, same output cap:
0.905 ± 0.071 in the original environment (n=15) and 0.913 ± 0.072 in the corrected one
(n=19). Difference +0.009, standard error 0.025 — an interval of roughly −0.040 to
+0.057. This is a failure to detect an effect at this power, **not evidence that there
is none**; anything below ~5 points would be invisible here.

**Differences that remain, declared**:

- **Our actions carry four fields** (`shelf`, `sku`, `units`, `lot`) against their
  positional two. There is more to get right per action, which cuts against the
  "our environment is easier" hypothesis. The failure adjudication (§6) quantifies it
  at 11 %.
- **Our observations are more verbose.** The match is by **context density**, not
  literal content. At T=200, ReAct's mean prompt is 58,127 tokens against their 48,007
  — **above theirs**.
- **Which empty shelf their ground truth picks in `Store`** is unspecified. We take the
  lowest-numbered free shelf. This is the one difference that requires asking the
  authors.

---

## 3. The capability ladder

Faithful environment, `gemini-3-flash-preview` via Vertex, `temperature=0`, `top_p=1`
(their settings). **Nineteen of the twenty cells are 15 runs** (5 seeds × 3
repetitions). The twentieth — ReAct at T=200 — carries 19 runs, distributed 3/3/7/3/3
across seeds because seed 2 was repeated four extra times while measuring run-to-run
noise (§6); its mean over the balanced 15 is 0.905 ± 0.079 and over all 19, 0.913 ±
0.072. In total, 299 episodes have per-step traces and five are aggregate-only. Their
Table 1 in parentheses.

> **Stateful was re-measured.** Its runner discarded every nested state patch — 40 of
> 5,775 responses produced an applied patch, 0.7 % — so its original cells measured full
> history plus a state block holding no inventory (§6, item 7). T=50 and T=200 below come from a re-measurement with the parser
> fixed (15 runs each, every trace recording the parser version; on Gemini the fixed
> parser applied 3,748 of 3,750 patches); T=10, 25 and 100, marked †, keep the defective
> measurement. No change was detected: 0.996 → 0.996 and 0.912 → 0.930 (+0.017, Welch
> 95 % interval −0.066 to +0.100). No change was detected, but substantial effects in
> either direction remain compatible with that interval — including one large enough to
> remove every failure of the old cells.

| T | ReAct | Memory | Stateful | SKILL.state |
|---|---|---|---|---|
| 10 | 0.993 ± 0.026 (0.90) | 1.000 ± 0.000 (1.00) | 1.000 ± 0.000† (1.00) | 1.000 ± 0.000 (1.00) |
| 25 | 0.955 ± 0.050 (0.92) | 0.987 ± 0.042 (0.99) | 1.000 ± 0.000† (1.00) | 1.000 ± 0.000 (1.00) |
| 50 | 0.936 ± 0.057 (0.88) | 0.953 ± 0.077 (0.93) | 0.996 ± 0.008 (0.94) | 1.000 ± 0.000 (0.96) |
| 100 | 0.960 ± 0.063 (0.84) | 0.839 ± 0.096 (0.87) | 0.995 ± 0.008† (0.91) | 1.000 ± 0.000 (0.94) |
| 200 | 0.913 ± 0.072 (0.74) | 0.810 ± 0.083 (0.84) | 0.930 ± 0.092 (0.88) | 1.000 ± 0.000 (0.94) |

Drop from T=10 to T=200 (ours / theirs): ReAct −0.080/−0.160 · Memory −0.190/−0.160 ·
**SKILL.state 0.000/−0.060**. Stateful loses 0.066 between T=50 and T=200 (theirs: 0.060).

**What reproduces.** Their central thesis, with room to spare: SKILL.state does not fail
**once in 75 episodes** of up to 200 steps. It is the only arm with zero degradation;
theirs loses six points. With this model, which does not hold on the second one (below).

**What does not.** The magnitude, and only for ReAct: it loses 0.080 where theirs loses
0.160, and **Memory loses more than theirs** (0.190 against 0.160). At T=200 our ReAct sits **17 points above** theirs, and the gap
widens with the horizon (+0.09 at T=10, +0.17 at T=200).

Reasoning effort, the output cap and the three environment gaps were each varied and
none accounts for it (§2, §6). The model is nominally theirs, but §7 records that
`gemini-3-flash-preview` may not be the checkpoint behind their `Gemini-3-Flash`, so we
cannot rule the model out either — only note that we did not change it.

**Where their ordering breaks.** Memory comes last in our environment; they place it
above ReAct. **This is a difference of ours, not a finding**: our summariser compresses to a
5,770-token mean prompt at T=200 (measured in the Appendix-B environment at the same
output cap; the faithful-environment cells were measured with an instrument that did
not record tokens, §6) where theirs occupies 84,364 — a factor of **14**. Their
"Memory (Summary)" barely summarises; it retains almost as much context as ReAct.

### The same protocol on a second model

Claude Haiku 4.5 via Microsoft Foundry, **with the environment and decision cap of the
table above** — faithful environment, output cap 8192 — but not its decoding: Gemini runs
with `temperature=0`, `top_p=1` and reasoning budget 0, while Haiku receives neither
setting (the SDK no longer accepts `temperature`) and runs without extended thinking. At
the two ends of the horizon, 3 seeds × 8
repetitions = **24 runs per cell**, every episode with a per-step trace and a conditions
header. Gemini's figures from the table above in parentheses.

| T | ReAct | Memory | Stateful | SKILL.state |
|---|---|---|---|---|
| 50 | 0.978 ± 0.045 (0.936) | 0.809 ± 0.184 (0.953) | 0.991 ± 0.026 (0.996) | 0.999 ± 0.004 (1.000) |
| 200 | 0.974 ± 0.070 (0.913) | 0.653 ± 0.157 (0.810) | **0.999 ± 0.002** (0.930) | **0.958 ± 0.058** (1.000) |

Stateful cells are 15 runs (3 seeds × 5); the rest, 24. Haiku's Stateful needed a third
parser version: the second still dropped the patches Haiku writes in Markdown
(`**StateUpdate:**` followed by a code block) — 731 of 3,000 at T=200, in 7 of 15
episodes — which an adversarial review found (§6, item 7). The cells above use the third,
which accepts 2,998 of 3,000 responses at T=200 and 749 of 750 at T=50; of those, five are
empty patches (`{}`, nothing to change), so 2,995 and 747 change the state. The three it
does not accept contain no object at all.

ReAct is flat on Haiku: −0.005 between T=50 and T=200, against −0.023 on Gemini and
−0.140 in the paper over the same interval. The full-history arm the paper shows
collapsing degrades on Haiku less than SKILL.state (−0.041); only Stateful degrades less.

**SKILL.state fails on Haiku, and the adjudication says where.** We replay the
environment with the actions the model executed and compare, step by step, the inventory
the model believes (SKU, units and lot per shelf) against the real one
(`experiments/adjudicar_estado.py`). A failure is attributed to the state only when the
believed inventory prescribes a **different** action than the real one and the model
executed exactly the action the believed inventory prescribes. "The belief matches
reality" means agreement on every field the model wrote; a field it left unspecified —
a shelf recorded only by its SKU, say — is not counted as a discrepancy. Of the 201
failures at T=200:

- **167 are caused by the state** in that sense; **17** occur while the belief differed
  from reality but the discrepancy does not explain them (both inventories prescribe the
  same action, or the model followed neither); **17** occur with a correct state.
- **In all 17 episodes where the belief departed from reality, the origin is the same:
  a `Move` executed correctly with a state patch written wrong.** `Move` is the only
  transition that requires copying one shelf's contents into another key of the state,
  and that copy is where it breaks — the model writes the contents of a different shelf,
  the lot of the pallet it stored one step earlier, or the wrong number of units.
- **Only in 7 of those 17 did the error reach a decision, all in seed 2.** In 6 of its
  8 runs the corruption happens at the same step (132), after which the model ships from
  a shelf that does not hold the SKU, cascades through ~25 state-caused failures and does
  not correct its state even when the environment rejects the action. In seed 0 the
  corrupted field is a lot number that no later decision reads: 8 corrupted runs, no
  failure caused by it.

What SKILL.state removes is the need to **reconstruct** the state from history. What it
introduces is the need to **write** it correctly at every transition, and nothing in the
runtime checks that the write matches what the action did. Gemini's belief never departed
from reality in any of its 75 episodes; Haiku wrote at least one wrong patch in 17 of 24
at T=200, and in 7 of them the error reached a decision. The paper's thesis survives in
direction — SKILL.state is still the best arm on Gemini and within 0.02 of ReAct on
Haiku — but "explicit state does not degrade" is a property of the model as much as of
the runtime.

**Stateful orders the two models in opposite directions.** At T=200 Stateful is the best
arm on Haiku (0.999, above SKILL.state's 0.958) and, on Gemini, is indistinguishable
from ReAct (0.930 against 0.913) and well below SKILL.state (1.000). The same
adjudication describes both — it describes, it does not separate causes, because
Stateful and SKILL.state also differ in response format, parsing, retries and prompt
construction, not only in carrying the history:

- **On Haiku, Stateful makes the same kind of write error as SKILL.state, far less
  consequentially, and loses nothing to it.** Its belief departs from reality in 8 of 15
  episodes at T=200 — always a correct action with a miswritten patch, the same failure
  as above — but the wrong state prescribes a different action on only 4 steps (against
  168 for SKILL.state), and on all 4 the model does what reality requires. **None** of
  its 2 failures is caused by the state; both happen with a correct one.
- **On Gemini it is the other way round.** Its belief departs from reality in 11 of 15
  episodes at T=200 (5 from a miswritten patch, 6 from a wrong action the state did not
  reflect), where SKILL.state on the same model never did in 75. Of its 211 failures, 86
  are caused by the state, 48 occur with a discrepancy that does not explain them, and
  **77 happen with a correct state in front of it**.

A hypothesis for why fixing the parser changed so little, which we have not tested: in
Stateful the model's responses go into the history, and each contains its own
`StateUpdate: {...}`. The transcript therefore carried a state written by the model
whether or not the runtime applied it, so the defective arm measured "state kept only in
the transcript" rather than "no state".

**Memory on Haiku runs into our summariser cap, and a control bounds — but does not
establish — what that costs it.** The summariser has its own output cap (1,200 tokens, with an instruction
to stay under 400 words). Gemini never reaches it — 0 truncated summaries in 30 episodes.
Haiku overruns it constantly: 194 truncated summaries in the 24 episodes at T=50 and
**2,386 at T=200**, about half of all summaries. A control arm at T=50 with the cap
raised to 4,096 (3 seeds × 3, `--summary-max-tokens`) truncates nothing and scores
**0.889 ± 0.126 (n=9) against 0.809 ± 0.184 (n=24)**: +0.080, Welch 95 % interval
−0.037 to +0.197. The control removes the truncation and raises the observed mean, but
does not establish an effect on the score, and raising the cap also changes how long a
summary may be, not only whether the same summary is cut. Uncut, Memory still stays well
below ReAct (0.978). Haiku's Memory column is therefore read as *our summariser with a cap one
model respects and the other does not*, and we draw no cross-model conclusion from it.

### Dense noise (their Experiment 2)

T=50 fixed, distractors appended to the observation under their header, 15 runs per
level:

| Noise (events/turn) | Our ReAct | Theirs |
|---|---|---|
| 0 | 0.961 ± 0.037 | 0.88 |
| 5 | 0.952 ± 0.066 | 0.68 |
| 20 | 0.959 ± 0.056 | 0.61 |
| 50 | 0.859 ± 0.121 | 0.53 |

From 0 to 50 events: **−0.103, 3.1 standard errors**. Theirs: −0.350. **The effect is real, and what we can
resolve is the extreme**: 0, 5 and 20 are not distinguishable at this sample size — their
means span 0.009 with standard deviations near 0.06 — so the measured effect is carried
by the jump to 50. A gradual decline of a few points across the lower levels would be
invisible here.
And what changes most is not the mean but the dispersion, which triples: under 50
distractors the model is not stably worse — it is **erratic**.

---

## 4. Cost accounting with caching

The paper compares **tokens**; whoever pays the bill compares **money**. An append-only
transcript caches almost entirely; a mutating state block invalidates the prefix.

Measured on Claude Haiku 4.5 via Microsoft Foundry (T=50, 3 seeds, caching on,
short procedure):

| Runtime | Score | Raw tokens | Effective cost | Cache saving |
|---|---|---|---|---|
| ReAct | 1.00 | 826k | **152k** | **82 %** |
| Stateful | 1.00 | 873k | 873k | 0 % |
| Memory | 0.87 | 313k | 313k | 0 % |
| SKILL.state | 1.00 | **109k** | 109k | 0 % |

**SKILL.state's advantage over ReAct goes from 7.54x in raw input tokens to 1.39x in
effective input**, and the ordering inverts: by tokens SKILL.state < Memory < ReAct <
Stateful; by effective input SKILL.state < **ReAct** < Memory < Stateful.

Two bounds on that number, both material:

- **These are input tokens, not a full invoice.** Output is not priced in. Mean output
  per episode is 5,740 tokens for ReAct and 9,674 for SKILL.state — neither zero nor
  equal, and they move the comparison in SKILL.state's disfavour.
- **It depends on the length of the static prefix.** With the long procedure (~4,900
  tokens, above the cacheable minimum), the arms that compress start caching too:
  SKILL.state saves 79 %, Memory 48 %, Stateful 22 %, and SKILL.state's advantage is
  2.51x rather than 1.39x. The conflict below is therefore **conditional on a short
  static prefix**, not a property of compression as such.

Three consequences:

1. **With a short static prefix, compressing and caching are in conflict.** Every
   method that compresses rewrites the prefix, and rewriting the prefix costs the
   cache. With a long static prefix the conflict softens: the fixed block caches even
   for the compressing arms.
2. **ReAct and Stateful send nearly the same content and are billed 5.7x apart.**
   ReAct saves 82 %, Stateful 0 %. This contrast does **not** isolate prompt order: the
   two runners also differ in whether the history is marked as a cacheable prefix (only
   ReAct marks it), and the Stateful figure was measured with the defective parser of §6
   (item 7), whose state block was empty and therefore constant. Order, cache marking
   and a mutating block are confounded here. **Isolated, the effect of order is 5.2x.**
   Stateful on Haiku at T=50, 3 seeds × 2 runs per arm, both arms marking the history
   as a cacheable prefix and sending the same content (~880k raw input tokens per
   episode); only the position of the state block changes. State first: 74 % of the
   input is cache *writes* and 22 % reads, an effective 869k per episode, a 1 % saving.
   History first: 91 % reads and 4 % writes, an effective 168k, an 81 % saving. Scores do
   not differ (0.997 and 1.000). One of the six state-first runs never applied a patch —
   it wrote shelf numbers as unquoted keys, which is not JSON — so its state block stayed
   constant and cached like the other arm (160k effective); excluding it, the ratio is
   6.0x. We report 5.2x because it is what the arm as specified cost, and 6.0x as the
   effect among runs whose state actually changed. Their Appendix A.3 template puts the state block first.
3. **It reconciles an anomaly in their table.** Their totals column sits ~3.5x below
   horizon × mean prompt at every horizon. With caching it fits: their totals would be
   billed, their mean prompt raw.

### The magnitude does not transfer across providers

Measured on Vertex with `gemini-3-flash-preview`, **within a single grid** (original
environment, output cap 600, reasoning budget 0, n=5 episodes per cell) so that the
comparison is not mixing conditions. The figure is cache-read tokens over total input
tokens:

| Runtime | T=25 | T=50 | T=100 | T=200 |
|---|---|---|---|---|
| ReAct | 1.1 % | 4.6 % | 6.8 % | **7.0 %** |
| Stateful | 0 % | 2.6 % | 4.3 % | 4.3 % |
| Memory, SKILL.state | 0 % | 0 % | 0 % | 0 % |

Implicit caching therefore **exists on Vertex and favours exactly the arms whose prefix
is append-only**, growing with the horizon — the same qualitative pattern as Anthropic,
an order of magnitude smaller: **7 % against 82 %**. Other grids in other conditions give
between 1 % and 16 % for ReAct; the spread across conditions is not characterised here.

Paired within that grid, the cost ratio barely moves:

| | Raw input | Effective input |
|---|---|---|
| T=50, ReAct / SKILL.state | 7.90x | **7.57x** |
| T=200, ReAct / SKILL.state | 29.16x | **27.32x** |

A direct probe adds nuance and a warning. Repeating an identical 13,346-token request,
one run read 12,262 cached tokens on the second call and a later run read none; issuing
eight calls whose prefix grows by ~3,300 tokens each, none read any. Implicit caching is
**opportunistic and not reproducible on demand**: our probes of the growing-prefix
pattern registered nothing while the grids of that same pattern registered 7 %. We report
the grid figures, which are the ones the experiment actually incurred. Probe outputs are
persisted in `results/probe_cache_vertex_*.json`.

> An earlier version of this section stated that Vertex has no implicit cache. It was
> wrong: it generalised from the identical-request probe, and the project's own grids
> contradicted it — 503,600 cached tokens in a single ReAct episode at T=200. A clean
> measurement of the wrong thing.

Explicit caching works (20,013 of 20,016 tokens discounted, and 13,343 of 13,346 in a
second run) but does not fit ReAct's pattern: its prefix grows every step, so an object
cached at step *k* covers a shrinking fraction of the prompt at step *k+n*. We did not
measure whether repeatedly rebuilding it pays off; the claim here is only that the
naive use — one fixed cached block — does not apply.

Resulting statement: **prefix caching helps only the append-only arms, in both providers,
and by an order of magnitude more on Anthropic. The inversion of the accounting we
measured there does not reproduce on Vertex, where 7.9x in tokens remains 7.6x in
effective input.**

---

## 5. Two probes on their declared limitations

The paper declares two limitations without measuring them. We measured them.

### L1: explicit state only protects what was anticipated

A fact arrives at step `t` and changes the correct action at `t+40`. Claude Sonnet 5
via the Anthropic API, **same seed × 8 repetitions**, each seed its own control:

| Condition | Accuracy on the dependent step | 95 % CI |
|---|---|---|
| No field to store it | 12 % (3/24) | 4–31 % |
| Free-form `notes` field | 21 % (5/24) | 9–40 % |
| Schema field naming the fact | **75 %** (18/24) | 55–88 % |
| Reminder attached to the observation | **83 %** (20/24) | 64–93 % |

The conditions split into two groups that do not overlap. **Giving it somewhere to go is
not enough: the somewhere has to say what to store.** An explicit-state runtime protects
against what its designer already anticipated — precisely limitation L1, now with a
number.

> This measurement **withdrew** an earlier recommendation of the project itself. With
> one run per seed, the free-form field scored 60 % and had become the practical advice
> ("leave a hatch in your schema"). With repetitions it is false.

### L2: retroactive invalidation

An announced fact stops being true later. Counted over **dependent steps**, not
episodes:

| Model | Runtime | Applies the correction |
|---|---|---|
| Haiku 4.5 | ReAct | 3/44 — 6.8 % |
| Haiku 4.5 | SKILL.state | **44/44 — 100 %** |
| Sonnet 5 | ReAct | 15/38 — 39.5 % |
| Sonnet 5 | SKILL.state | **49/49 — 100 %** |

**Explicit state does not fail once: 93 of 93 dependent steps.** Full history gets 18 of
82. Two conditions of that count, from the source measurement: episodes with more than
three truncated responses are excluded (six Sonnet/ReAct episodes), and the SKILL.state
column counts only the dependent steps — the same runs recorded 21 other failures, 10
steps with no action and 66 invalid patches in Sonnet. The 100 % characterises
retroactive invalidation, **not** the runtime's overall reliability. And ReAct's
failure is all-or-nothing per scenario: in Haiku it misses all 11 dependent steps of one
episode, all 7 of another, all 4 of a third. This is not an agent that slips; it is a
flawless agent that **never updated a fact**.

### Both probes on the third model

Repeated on `gemini-3-flash-preview` via Vertex. **L1** uses the same output cap and
reasoning budget as Table 1 (8192 / 0), 3 seeds × 8 repetitions per cell. **L2** uses cap
8192 with the provider's default reasoning — its runner does not expose the budget flag —
and 3 seeds × 2 repetitions:

| L1 condition | ReAct | SKILL.state |
|---|---|---|
| No field to store it | 0/24 = 0 % [0–14] | 0/24 = 0 % [0–14] |
| Free-form `notes` field | 0/24 = 0 % [0–14] | **0/24 = 0 % [0–14]** |
| Schema field naming the fact | 0/24 = 0 % [0–14] | **16/24 = 67 % [47–82]** |
| Reminder on the observation | **16/24 = 67 % [47–82]** | 8/24 = 33 % [18–53] |

The floor is **zero in every run**, where in Claude it was a noisy 12 %; its Wilson
interval still admits up to 14 %, so "zero" describes the sample, not the population. The
intervals of the working conditions do not overlap it. Three things follow, with one
caveat stated first: **the successes concentrate by scenario, not by trial.** Per seed,
SKILL.state with the schema field scores 0/8, 8/8, 8/8, and with the reminder 0/8, 8/8,
0/8. Binomial intervals over 24 runs do not capture the uncertainty of generalising to
new scenarios, and the 67 %-vs-33 % difference between those two conditions comes
entirely from one seed.

- **The free-form field fails in both models.** 0/24 in Gemini, indistinguishable from
  having no field at all. The recommendation this project once made and then withdrew
  ("leave a hatch in your schema") finds no support in either model.
- **Naming the field works** (67 %), reproducing L1: explicit state protects what its
  designer anticipated.
- **The reminder works for the runtime that has nowhere to store anything.** ReAct with
  the fact attached to the observation reaches the same 67 % that SKILL.state reaches
  with a dedicated schema field. For SKILL.state the reminder scores lower than its own
  schema field (33 % against 67 %), but that gap rests on a single seed and we do not
  claim it.

L2 on the same model, counted over dependent steps:

| Model | ReAct applies the correction | SKILL.state |
|---|---|---|
| Haiku 4.5 | 3/44 | 44/44 |
| Sonnet 5 | 8/44 | 44/44 |
| **Gemini 3 Flash** | **0/44** | **44/44** |

**132 of 132 dependent steps with explicit state, across three models and three
services, against 11 of 132 with full history.**

Gemini is the model that never updates a fact — 0 of 44 — while scoring 0.913 on the
long procedure. Haiku, measured now under the same conditions as Gemini's Table 1 (§3),
scores **0.974** on that procedure at T=200 and still misses 41 of 44 corrections. The two
L2 measurements do not share every setting (§7), so we do not rank the models on it;
what holds on both is that **the long-procedure score does not predict this failure, and
within each model the runtime decides it.**

**Declared scope**: L1 in Gemini is measured with reasoning budget 0, matching Table 1;
the Claude measurements predate that control and use each provider's default.

---

## 6. Instrument and artefacts

This is the section that separates this from a blog post, and the one that cost us most.

**Nine artefacts catalogued** in the first block, all with the same signature: an
implicit contract between runtime and model. The runtime assumed something it never
declared, and the result depended on whether the model guessed right. The first three
cost entire grids; **two surfaced in the audit before publication, and both had produced
a written result, with tables and intervals, ready to send**.

This second block added six more, and they are worth enumerating because they transfer:

1. **Greedy decoding does not guarantee reproducibility.** The protocol assumed that at
   `temperature=0` seeds are environment instances and one run per cell suffices. The
   same cell repeated five times gives between 0.830 and 0.960. **Three already-written
   conclusions collapsed on repetition**: an environment effect of −5.8 points that
   turned out to be +0.008, a "monotonic" noise curve that turned out flat, and a
   noise estimate of eleven points that turned out to be a tail.
2. **The distribution has a left tail because failures cascade.** Across five runs of one
   cell the sample deviation is 0.052; **excluding the 0.830 outlier** it is 0.012, and
   three runs of the same cell at T=100 give 0.006. We quote both, because the second
   number is conditional on removing the very run that motivates the point. What forces
   repetition is not the ordinary spread: it is the tails.
3. **The runner discarded the model's responses.** It kept the score and the token
   counts, so `correct=False` was an indistinguishable zero: you could not tell whether
   the model lost track of state — what the experiment measures — or miscopied a JSON
   field. With responses retained, adjudicating 45 failures across four traces of one
   cell gives **32 wrong-shelf (71 %), 7 wrong action type (16 %), 5 field-copy errors
   (11 %), 1 unparseable**.
4. **A truncated episode counted as complete.** Aggregation counted files, not steps; an
   episode of 163 steps out of 200 entered the mean. The bias was two thousandths, but
   it was only found because completeness was checked as a matter of routine.
5. **Traces that did not record their own conditions.** For most of this work the traces
   stored no output cap, reasoning budget, provider or responding model ID. Two files
   from the same cell could come from different caps and nothing would say so — which is
   how a −5.8-point "environment effect" survived long enough to be written down. The
   runners now write a conditions header and per-step token usage — but **only runs made
   after that change carry it**. The 366 historical Gemini traces — Table 1 except the
   Stateful re-measurement, the noise table and the environment comparison — do not, so
   their conditions are certified by the filename and the run log, not by the artefact
   itself. Every trace behind the Haiku table, both Stateful re-measurements, the Memory
   control and the prompt-order experiment does.
6. **A probe that measured the wrong pattern.** The cache probe repeated an identical
   request and concluded that Vertex has no implicit cache, while the project's own
   grids recorded 503,600 cached tokens in one episode. The probe was correct; the
   pattern it probed was not the one the experiment uses.

A third block, found while measuring the second model, contains the most expensive
artefact of the project:

7. **One of the four arms never ran.** Stateful read its state patch with a non-greedy
   regex that stopped at the first closing brace. Every nested patch — the normal case,
   `{"shelf_contents": {"3": {...}}}` — was truncated, failed to parse, and was dropped
   without a warning: **40 of 5,775 responses on Gemini produced an applied patch, 0 of
   6,000 on Haiku**. What both
   Stateful columns measured is full history plus a state block with no inventory — empty
   on Haiku, and on Gemini holding only the occasional `last_event` (the 40 patches, in
   11 episodes). Its unit test
   used a flat value and passed. It surfaced only because Stateful beat SKILL.state on
   Haiku and we went to the traces to find out why. Re-measured with the parser fixed,
   no change was detected (§3). The first fix was itself incomplete: on Haiku it still
   dropped every patch written in Markdown — 731 of 3,000 at T=200 — which the third
   adversarial review found, not us; a third parser version closed it. A defect that
   changes nothing measurable is still a defect in what the column claims to measure.
8. **A cap one model respects and the other does not.** The summariser's own cap was
   never reached on Gemini and was exceeded in half the summaries on Haiku (§3). A cap
   is not a neutral constant across models; it has to be checked per model, in the
   traces.
9. **Resuming re-paid finished work.** The completeness check counted the conditions
   header as a step, so no episode ever matched its horizon and every relaunch re-ran
   episodes already measured. It was caught on the first relaunch of R2 because a cell
   finished minutes earlier started again.
10. **The traces did not record cache writes.** The client received them; the trace row
    did not store them. In the first run of the prompt-order experiment the arm that
    rewrites its cache every step — the most expensive case — showed ~540 prompt tokens
    per step and looked the cheapest. Those twelve episodes were discarded and re-run.
    The §4 table does not depend on it: it was computed by the grid runner, which counted
    writes.

Items 5 and 6 were found by an **independent adversarial review of this draft against
the raw traces**, not by us. That review also corrected the failure classification
above, the maintenance-event range in §2, the compression factor in §3 and the sample
size in §3. We recommend the procedure, not the anecdote: have something recompute every
published figure from the artefacts, without access to the prose that justifies it.

Why traces matter, verbatim from one episode: at step 12 the model stores the SKU of a
different pallet; at step 16 it asserts *"Shelf 0 (SKU-F, stored in step 12)"* when it
had itself stored SKU-B there. **The early error contaminates later decisions** — and
that, not sampling noise, is what produces the tail.

**The transferable claim**: the paper treats the runtime as neutral infrastructure — a
merge operator, a patch format, a schema, a prompt order. In this project, individual
runtime decisions moved results by amounts comparable to or larger than the difference
between the methods being compared: the schema field decides 0 % versus 67 % on the
dependent step (§5), and a parser that silently dropped state patches decided what one
of four arms measured for the whole project (§6, item 7). We have not measured every such
decision, so we make no claim about a general range.

**Repository artefacts**: environment with fidelity flags, per-step traces, completeness
verifier, a density meter that does not call the API, truncation counters, per-episode
checkpointing and end-to-end cache accounting.

---

## 7. Limitations

- **`gemini-3-flash-preview` may not be their `Gemini-3-Flash`.** Declared as a risk
  from the outset. Vertex returns the responding model ID on every call and it is
  recorded per step, but not in the traces measured before that change. The Anthropic
  client did not copy it until the last Stateful re-measurement: from then on — its 30
  episodes and the prompt-order experiment — every step records
  `claude-haiku-4-5-20251001`; the earlier Haiku traces record only the requested alias
  in their header.
- **A reimplemented environment is not their environment.** We matched what their
  appendix allows us to compare, and the remaining differences are in §2. The shelf
  choice in `Store` still awaits an answer from the authors.
- **Our Memory is not comparable to theirs.** Our summariser compresses fourteen times
  more (5,770-token mean prompt against their 84,364 at T=200).
  What we measured is our summarisation policy, not "summarisation" as a category.
- **We have not proven the environment gaps have no effect**; we measured that, at the
  power available, none above ~5 points is detectable. The same caveat applies to the
  three lowest noise levels in §3.
- **Cell sizes are not uniform.** Nineteen cells carry 15 runs; ReAct at T=200 carries
  19, unbalanced across seeds (3/3/7/3/3). Five of its episodes exist only as
  aggregates, without traces.
- **Cost figures price input only**, and the caching results depend on the length of the
  static prefix (§4).
- **The probes now cover all three models**, across three services (Vertex, the
  Anthropic API and Microsoft Foundry), but not under identical settings: L1 on Gemini
  fixes the reasoning budget at 0 to match Table 1; L2 uses the provider default because
  its runner does not expose the flag; and the Claude runs predate that control. Their
  counts carry the exclusions listed in §5.
- **One environment.** The second (Software Repository) was retired: it did not
  discriminate between runtimes and would have added noise without information.
- **SKILL.state's ceiling depends on the model.** At 1.000 with zero variance on Gemini
  the task did not discriminate at the top; on Haiku it does (0.958 at T=200), and the
  failure is in writing the state (§3). Two models are not enough to say which models
  make that error.
- **Stateful has been re-measured only at T=50 and T=200**, with parser version 2 on
  Gemini (which applied 3,748 of 3,750 of its patches) and version 3 on Haiku. The
  intermediate horizons of Gemini's Table 1 keep the defective measurement, marked as
  such.
- **Haiku and Gemini do not share decoding settings** (§3): the cross-model differences
  are between two configured systems, not two models under identical conditions.
- **Haiku's Memory column mixes the summarisation policy with summary truncation** (§3);
  the control arm has n=9 and bounds the effect at T=50 only.
