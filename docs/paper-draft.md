# The Runtime Is Not Infrastructure: A Replication of SKILL.state

**Draft.** Every figure comes from a measurement in this repository, with per-step
traces and raw data on the `runs/table1-gemini-3-flash-preview-vertex` branch.

---

## 1. What the paper claims, and what we measured

[SKILL.state](https://arxiv.org/abs/2608.26263) argues that an agent maintaining
**explicit state** executes long procedures far better than one carrying the whole
conversation, and that the gap widens with the horizon. Its Table 1 shows this with
Gemini-3-Flash in a simulated warehouse: ReAct falls from 0.90 to 0.74 between 10 and
200 steps while SKILL.state falls only from 1.00 to 0.94.

We reimplemented their environment from the paper's description — SkillExecBench is not
public — and measured three things:

1. **Whether the ladder reproduces** under their own model and decoding settings (§3).
2. **What each runtime actually costs** when you count money rather than tokens (§4).
3. **What explicit state protects against**, through two probes: one on a limitation the
   paper declares (a state schema only protects what it anticipates) and one revisiting
   its recovery experiment with a retroactive correction (§5).

The short version: **their thesis holds and their magnitude does not; and once input is
billed with caching, SKILL.state's cost advantage over full history shrinks from 7.5x to
1.4x on Anthropic with a short static prefix** — it stays the cheapest arm, and on Vertex
the advantage barely moves. Explicit state protects against losing track of
the procedure; on a second model it does not protect against **writing the state
wrong** — here a semantic copying error in schema-valid patches, a more specific
mechanism than the structural and formatting errors of the paper's own error taxonomy —
and that is what ends up limiting it.
And the largest effects in the whole experiment come not from any of the compared
methods, but from runtime implementation decisions the paper treats as neutral: one of
them silently disabled one of our four arms in every measurement made before we fixed it
(§6).

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
is none**; effects of several points in either direction remain compatible with it.

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

**What does not.** The magnitude, in both directions: ReAct loses 0.080 where theirs
loses 0.160, SKILL.state loses nothing where theirs loses 0.060, and **Memory loses more
than theirs** (0.190 against 0.160). At T=200 our ReAct sits **17 points above** theirs, and the gap
widens with the horizon (+0.09 at T=10, +0.17 at T=200).

Reasoning effort, the output cap and the three environment gaps were each varied and
none accounts for it (§2, §6). The model is nominally theirs, but §7 records that
`gemini-3-flash-preview` may not be the checkpoint behind their `Gemini-3-Flash`, so we
cannot rule the model out either — only note that we did not change it.

**Where their ordering breaks.** At T=100 and T=200 Memory comes last in our environment;
they place it above ReAct. (At T=10–50 our Memory is above ReAct, as theirs is.) **This is a difference of ours, not a finding**: our summariser compresses to a
5,770-token mean prompt at T=200 (measured in the Appendix-B environment at the same
output cap; the faithful-environment cells were measured with an instrument that did
not record tokens, §6) where theirs occupies 84,364 — a factor of **14**. Their Memory's
reported mean prompt at T=200 is about 76 % *larger* than their ReAct's (84,364 against
48,007); prompt size alone does not say what their summariser keeps, so we draw no
conclusion about its mechanism.

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
by the jump to 50. Among the lower levels no difference was detected (−0.009 and −0.003
against zero noise, intervals roughly ±0.04), and declines of several points remain
compatible with the data.
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
3. **It suggests one reading of an anomaly in their table, which we cannot verify.**
   Their totals column sits 2.7x to 3.7x below horizon × mean prompt across all twenty
   cells. Caching is one hypothesis — totals billed, mean prompt raw — but their table
   labels the totals as tokens consumed and gives no cache breakdown; the discrepancy is
   unexplained until the authors say otherwise.

### The magnitude does not transfer across providers

Measured on Vertex with `gemini-3-flash-preview`, **within a single grid** (original
environment, output cap 600, reasoning budget 0, n=5 episodes per cell) so that the
comparison is not mixing conditions. The figure is cache-read tokens over total input
tokens:

| Runtime | T=25 | T=50 | T=100 | T=200 |
|---|---|---|---|---|
| ReAct | 1.1 % | 4.9 % | 7.3 % | **7.5 %** |
| Stateful | 0 % | 2.8 % | 4.7 % | 4.8 % |
| Memory, SKILL.state | 0 % | 0 % | 0 % | 0 % |

Implicit caching therefore **exists on Vertex and favours exactly the arms whose prefix
is append-only**, growing with the horizon — the same qualitative pattern as Anthropic,
an order of magnitude smaller: an input-cost saving of **6.8 % against 82 %** for ReAct.
Other grids in other conditions give other figures for ReAct; the spread across
conditions is not characterised here.

> These Vertex figures were first computed counting cached tokens twice: Gemini's
> `promptTokenCount` already includes them, and the client stored them again as cache
> reads (§6, item 12). The corrected figures above move the ratios by about 0.4x at T=50
> and 2x at T=200; the qualitative conclusion does not change.

Paired within that grid, the cost ratio barely moves:

| | Raw input | Effective input |
|---|---|---|
| T=50, ReAct / SKILL.state | 7.53x | **7.20x** |
| T=200, ReAct / SKILL.state | 27.12x | **25.28x** |

A direct probe adds a warning. The archived run (`results/probe_cache_vertex_*.json`)
repeats an identical 13,346-token request twice and issues six calls whose prefix grows
by ~3,300 tokens each: **none of the eight reads a single cached token**, while the grids
of that same growing pattern registered 7 %. Implicit caching is **opportunistic and not
reproducible on demand**. We report the grid figures, which are the ones the experiment
actually incurred. (An earlier probe run, whose output was not archived, read cached
tokens on the repeated request; we do not cite its figures.)

> An earlier version of this section stated that Vertex has no implicit cache. It was
> wrong: it generalised from the identical-request probe, and the project's own grids
> contradicted it — 503,600 cached tokens in a single ReAct episode at T=200. A clean
> measurement of the wrong thing.

Explicit caching works (13,343 of 13,346 tokens discounted in the archived run) but does
not fit ReAct's pattern: its prefix grows every step, so an object
cached at step *k* covers a shrinking fraction of the prompt at step *k+n*. We did not
measure whether repeatedly rebuilding it pays off; the claim here is only that the
naive use — one fixed cached block — does not apply.

Resulting statement: **with a short static prefix, prefix caching helps only the
append-only arms, in both providers, and by an order of magnitude more on Anthropic;
with a long enough immutable prefix it helps the compressing arms too (SKILL.state
saves 79 % and Memory 48 %, above). The shrinking of SKILL.state's advantage measured on
Anthropic does not reproduce on Vertex, where 7.5x in tokens remains 7.2x in effective
input.**

---

## 5. Two probes on what explicit state protects against

L1 measures a limitation the paper declares without measuring it: that an explicit
state helps only with what its schema anticipated. L2 revisits the paper's recovery
experiment (its Experiment 3, an external change followed by a corrective observation)
with a correction that retroactively invalidates an announced fact.

### L1: explicit state protects best what was anticipated

A fact is announced at step `t` and first changes the correct action at step `t+40`.
Both halves of that sentence are now checked rather than assumed. The generator accepts a
scenario only if, with the notice in place and the correct policy, the fact changes the
action for the **first** time exactly 40 steps later (14 of seeds 0–39 qualify; we use
the first three, 0, 3 and 6). And on each episode's **real** trajectory we check that the
scored step still depends on the fact; when the agent's earlier choices have already
changed the world so that it does not, the episode tests nothing and is reported apart,
never as a success. All three models, T=50, 8 repetitions per seed, output cap 8192
(Gemini with reasoning budget 0), Claude via Microsoft Foundry and Gemini via Vertex.
Successes over the episodes where the test materialised, Wilson 95 % intervals:

| SKILL.state | Haiku 4.5 | Sonnet 5 | Gemini 3 Flash |
|---|---|---|---|
| No dedicated field | 0/24 [0–14 %] | 4/16 [10–49 %] · 4/24 | 0/24 [0–14 %] |
| Free-form `notes` field | 10/24 [24–61 %] | 6/15 [20–64 %] · 6/24 | 1/24 [1–20 %] |
| Schema field naming the fact | **24/24 [86–100 %]** | **16/16 [81–100 %]** · 16/24 | **16/24 [47–82 %]** |
| Reminder attached to the observation | **24/24 [86–100 %]** | **15/15 [80–100 %]** · 15/24 | 0/24 [0–14 %] |

ReAct has no schema, so the first three conditions send it the identical prompt; pooled
they are 72 replicates of one cell. Its reminder condition is the only one that changes
what it sees:

| ReAct | Haiku 4.5 | Sonnet 5 | Gemini 3 Flash |
|---|---|---|---|
| No reminder (pooled) | 1/72 [0–7 %] | 21/62 [23–46 %] · 21/72 | 0/72 [0–5 %] |
| Reminder on the observation | **23/24 [80–99 %]** | **18/19 [75–99 %]** · 18/24 | **17/24 [51–85 %]** |

On Haiku and Gemini every episode materialised. On Sonnet 2–9 of the 24 episodes per
cell did not — its trajectory had already diverged by step `t+40` — so its cells show
two rates: successes over the episodes where the test materialised, and, after the dot,
the episodes that both materialised the test and answered it correctly, over all
attempted episodes (24, or 72 for pooled ReAct). The excluded episodes are not counted as successes, although 28
of them happened to take the right action. **The two rates answer different questions,
and the conditional one flatters.** Whether an episode materialises depends on what the
runtime did before, so conditioning on it changes the population and its mix of
scenarios between arms: Sonnet's SKILL.state with the named field looks perfect at 16/16
but materialises the test and answers it correctly in 16 of 24 attempts, exactly Gemini's
16/24; and with the reminder Sonnet's SKILL.state looks better than its ReAct (15/15
against 18/19) but the order reverses on that joint measure (15/24 against 18/24). We read Sonnet's conditional
cells as retention given that the test happened, not as an overall advantage. Only 1 of
the 576 episodes saw the fact change the correct action before `t+40`.

What holds across the three models:

- **Naming the field is what works best.** The named field takes SKILL.state from 0–25 %
  to 67–100 % (conditional rates). A free-form `notes` field helps on the two Claude
  models (Haiku 42 %, Sonnet 40 %) and not on Gemini (4 %), and on every model it stays
  far below the named field. "No dedicated field" does not mean nowhere to store the
  fact: the schema checks only top-level keys, and all four of Sonnet's successes in that
  arm wrote the quarantine into `shelf_contents` itself (`{"9": {"blocked": true}}`) and
  used it forty steps later. What the named field adds is a dedicated place **and** the
  cue that the fact belongs there; these experiments do not separate the two. An
  explicit-state runtime protects best against what its designer already anticipated —
  limitation L1, with a number.
- **A reminder works for the runtime that has nowhere to store anything.** ReAct goes
  from 0–34 % to 71–96 % when the fact travels with the observation.
- **But the reminder does not transfer to the explicit-state runtime on every model.**
  On Gemini, SKILL.state with the reminder scores 0/24 while ReAct with the same reminder
  scores 17/24. We report it and do not explain it.
- **The successes concentrate by scenario, not by trial.** Gemini's SKILL.state with the
  named field scores 0/8, 8/8, 8/8 across seeds 0, 3 and 6, and Sonnet's ReAct without a
  reminder succeeds almost only on seed 6 (its notice arrives at step 0, the first
  message of the history). Binomial intervals over 24 runs understate the uncertainty of
  generalising to new scenarios.

> **Three versions of this probe.** Version 1 applied the correct action whenever the
> runtime returned none. Version 2 fixed the runner but kept the scenarios, which took the
> latest step at which the quarantined shelf would be the lowest free one and put the
> notice 40 steps before it without checking the steps in between: in two of its three
> seeds (1 and 2) the fact mattered 5 and 8 steps after the notice, so those cells
> measured continuous rather than delayed relevance, and in 59 of 576 episodes the scored
> step did not depend on the fact at all (45 were counted as successes). Version 3, above,
> uses strict scenarios on seeds 0, 3 and 6. Between versions 2 and 3 some cells moved —
> ReAct without a reminder on Haiku from 10/72 to 1/72, SKILL.state with the reminder on
> Gemini from 8/24 to 0/24 — but the scenario sets differ (seeds 0/1/2 against 0/3/6), and
> nine of those ten Haiku successes and all eight Gemini ones were on the removed seed 1.
> The changes are results on different scenarios, not an isolated effect of delay. This probe also **withdrew** an older
> recommendation of the project: with one run per seed, the free-form field had scored
> 60 % on Sonnet and become the practical advice ("leave a hatch in your schema").

### L2: retroactive invalidation

An announced fact stops being true later, and the agent has to act on the correction.
In the three scenarios used here (seeds 4, 10 and 6) a correct trajectory has **exactly
one step the correction decides** — a property of these scenarios, not of the generator,
which in other seeds yields none or several; once an
agent misses it, its world diverges and further steps start to disagree with the truth,
so counting them scores the cascade, not the correction. The measure is therefore per
episode: does the agent get the decisive step right? All three models at T=50, seeds 4,
10 and 6 × 8 repetitions, output cap 8192 (Gemini with reasoning budget 0), Claude via
Microsoft Foundry and Gemini via Vertex:

| Model | ReAct applies the correction | SKILL.state |
|---|---|---|
| Haiku 4.5 | 1/24 | **24/24** |
| Sonnet 5 | 9/24 | **22/24** |
| Gemini 3 Flash | 0/24 | **24/24** |

**Explicit state applies the correction in 70 of 72 episodes (97 %, Wilson 95 % interval
90–99 %); full history in 10 of 72 (14 %, 8–24 %).** Every episode had its decisive step,
and no response was truncated at it — seven Sonnet/ReAct episodes truncated elsewhere,
and none was excluded. The misses are not other errors: every failed decisive step is
exactly the action of an agent that never heard the correction. The successes
concentrate by scenario rather than by trial — Sonnet with ReAct scores 2/8, 0/8 and
7/8 across the three seeds, and its two SKILL.state misses are both in seed 4 — so the
binomial intervals understate the uncertainty of generalising to new scenarios.

> **This replaces an earlier measurement that did not measure what it published.** The
> previous version of this section reported "93 of 93" and "132 of 132" dependent steps
> with explicit state. Its scorer took the dependent steps from the trajectory of a
> *simulated* deaf agent, counted successes as dependent steps minus deaf actions without
> deducting steps with no action or with another error, and its runner applied the
> *correct* action whenever the runtime returned none. A runtime that never answers
> scored 100 % (§6, item 11). The direction survives; the perfection does not.

### Across the three models

Gemini with ReAct never applies either correction — 0 of 72 in L1 without a reminder, 0
of 24 in L2 — while scoring 0.913 on the long procedure; Haiku scores 0.974 at T=200 and
applies the L2 correction once in 24. **High long-procedure scores coexist with poor
probe performance on Haiku and Gemini, and probe performance differs sharply between
runtimes on all three models.** We did not measure Sonnet's long procedure, and we make
no predictive claim across models. Both probes are measured with the same cap and design on the three models;
their decoding still differs between providers (§3).

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
   after that change carry it**. The historical Gemini traces — Table 1 except the
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

11. **A probe that could not fail.** The first L2 scorer counted dependent steps on a
    simulated trajectory and subtracted only deaf actions, and its runner repaired the
    world whenever the runtime returned no action; a runtime that never answers scored
    100 %. It was the section of this draft we had checked least, because its result was
    the cleanest. The fifth adversarial review found it. Re-measured with the decisive
    step read from the real trajectory, explicit state goes from "132 of 132" to 70 of
    72 episodes. L1 had the same world-repairing runner and a second defect of design,
    found by the sixth review: its fact was not delayed in two of its three scenarios.
    It was redesigned and re-measured (§5).

12. **Two providers, two meanings of "prompt tokens".** Anthropic's `input_tokens`
    excludes cached tokens; Gemini's `promptTokenCount` includes them. The client stored
    both the same way and the cost function added cached tokens on top, so every Vertex
    cost figure counted the cache twice. The eighth adversarial review found it; the §4
    Vertex figures are recomputed.

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
of four arms measured until it was fixed (§6, item 7). We have not measured every such
decision, so we make no claim about a general range.

**Repository artefacts**: environment with fidelity flags, per-step traces, completeness
verifier, a density meter that does not call the API, truncation counters, per-episode
checkpointing and end-to-end cache accounting — except in the L1 aggregates, whose cost
fields ignored cache reads and writes until the last re-measurement, and in every Gemini
figure computed before item 12 below, which counted cached tokens twice. The per-step
traces record the raw provider fields and are the source to use.

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
- **We have not proven the environment gaps have no effect.** The measured difference is
  +0.009, with an interval of roughly −0.040 to +0.057 (§2): no change was detected, and
  effects of several points in either direction remain compatible. The same caveat
  applies to the three lowest noise levels in §3.
- **Cell sizes are not uniform.** Nineteen cells carry 15 runs; ReAct at T=200 carries
  19, unbalanced across seeds (3/3/7/3/3). Five of its episodes exist only as
  aggregates, without traces.
- **Cost figures price input only**, and the caching results depend on the length of the
  static prefix (§4).
- **The probes share cap and design across models, not decoding.** Both were re-measured
  on all three models with the corrected runner (§5); Gemini runs with temperature 0 and
  reasoning budget 0, Claude without either setting.
- **One environment.** The second (Software Repository) was retired because it could not
  measure what it was built for, not because the arms scored alike — they did not
  (Haiku: SKILL.state 0.974, ReAct 0.895; Sonnet: 0.876 and 1.000, 9 episodes each). Its
  dependency always sat exactly two steps after the event that created it, so it had no
  delayed relevance to measure (`docs/resultados-bloque1.md`, §4.ter). We do not
  attribute the score differences above to rule or routine steps: a separate diagnostic
  sample of three episodes per arm shows both kinds of failure, and the nine-episode
  cohorts themselves were not adjudicated.
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
