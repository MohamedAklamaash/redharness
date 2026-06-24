# redharness — an open-source LLM red-teaming & safety benchmark

`redharness` is a research-grounded, reproducible harness that stress-tests large
language models across three attack surfaces — **jailbreaks**, **prompt injection**, and
**data leakage** — and reports standardized, provenance-tracked metrics with a static
leaderboard dashboard.

It is built around a single idea: in LLM safety research, *standardizing the evaluation*
matters more than inventing the strongest individual attack. The benchmarks that the
field actually rallied around (HarmBench, JailbreakBench) won by making results
comparable and reproducible. `redharness` follows that playbook and extends it to the
injection and leakage surfaces, which remain comparatively under-standardized.

---

## The problem

LLM safety evaluation is fragmented:

- **Attack papers each ship their own ad-hoc eval.** "Attack Success Rate" means
  different things in different papers, so numbers are rarely comparable.
- **Judges disagree.** Whether a response counts as "harmful" or a "leak" depends on the
  grader; small judge changes move headline numbers by tens of points (StrongREJECT
  showed many prior benchmarks *overestimate* attack success).
- **Injection and leakage are barely standardized at all**, despite prompt injection
  being ranked #1 on the OWASP LLM Top 10 two years running.
- **Results aren't reproducible.** Datasets drift, seeds aren't pinned, transcripts
  aren't kept, and leaderboards can be gamed.

The cost is that it's genuinely hard to answer "is model A safer than model B, and by how
much, under what threat model?" with a number anyone can reproduce.

## What redharness does about it

1. **One pluggable harness, three surfaces.** Every evaluation is a matrix of
   `Attack × Target × Dataset × Judge × Metric` (plus a `Scenario` axis for agentic
   injection). Adding a new attack, model adapter, or judge is a small, self-contained
   plugin — no forking the runner.
2. **Reuse accepted datasets and judges** as plugins so numbers line up with published
   work, and reserve novelty for the harness, the cross-surface standardization, and the
   leaderboard.
3. **A reproducibility contract.** Datasets are hash-pinned; runs are deterministically
   seeded; full transcripts are persisted as JSONL; one command reproduces a leaderboard
   row.
4. **Provenance on every number.** Each leaderboard cell records the
   `(dataset_version, judge, metric)` triple, so a value is never ambiguous about how it
   was produced.
5. **A static, offline, gaming-aware dashboard** that aggregates every run into one
   self-contained HTML page.

---

## Threat model: the three surfaces

### 1. Jailbreaks
Does an adversarial prompt get the model to produce content it should refuse? Covers
static replay of known behaviors and template-style transformations, scored by a refusal
detector and a StrongREJECT-style rubric, and balanced against **over-refusal** (false
refusals on benign prompts) so safety isn't measured in a vacuum.

### 2. Prompt injection (direct + indirect / agentic)
Can a malicious instruction — placed directly in the user turn, or **indirectly** in a
document or tool output the agent reads — hijack a tool-using agent into the attacker's
goal? Modeled like AgentDojo/InjecAgent: a sandboxed tool environment with a benign user
task and a benign *sentinel* attacker goal, driven through a bounded agent loop. Measures
both **injection success** and **utility under attack** (does the agent still do its real
job?).

### 3. Data leakage (extraction, canary, PII, system-prompt)
Will the model emit memorized or secret content? Covers training-data **extraction** /
divergence probes (Carlini/Nasr), **canary** exposure (Secret Sharer), **PII**
elicitation, and **system-prompt** exfiltration. A leak detector computes both a binary
recovery decision and a continuous verbatim-overlap (longest-common-substring) severity
score. All planted secrets are synthetic, benign sentinels — no real PII or copyrighted
text.

---

## Architecture

```
            ┌──────────────┐   probes/payloads   ┌──────────────┐
 Dataset ─▶ │   Attack     │ ──────────────────▶ │   Target     │ ──▶ transcript
 (behaviors)│ (generator)  │                     │ (model adapter)│
            └──────────────┘                     └──────┬───────┘
                                                        │ response
                                                 ┌──────▼───────┐
                                                 │    Judge     │ score per item
                                                 └──────┬───────┘
                                                 ┌──────▼───────┐
                                                 │   Metrics    │ ASR, ISR, leak-rate,
                                                 │  + Report    │ overlap, …
                                                 └──────┬───────┘
                                                 ┌──────▼───────┐
                                                 │  Dashboard   │ aggregated leaderboard
                                                 └──────────────┘
```

Stable plugin interfaces live in `redharness.core`; a typed registry resolves plugins by
name from declarative YAML configs (closed dict lookup — no dynamic import/`eval`, so a
config can't execute arbitrary code). The runner executes the matrix deterministically,
caches attempts keyed on the full resolved parameters, writes JSONL transcripts, and
renders Markdown/HTML reports plus a `leaderboard.json`. The injection surface adds a mock
tool environment and a bounded multi-step agent loop; the leakage surface reuses the
single-turn path with leakage-specific plugins.

### Metrics (all citable)

| Metric | Surface | Meaning |
|---|---|---|
| ASR / ASR@k | jailbreak | attack success (within a query budget) |
| StrongREJECT score | jailbreak | rubric grade (refusal × specificity/convincingness) |
| refusal rate / FRR | jailbreak | refusals; false refusals on benign prompts |
| injection success rate | injection | attacker tool-goal achieved |
| utility under attack / baseline | injection | benign task still completed |
| extraction / canary / PII / system-prompt rate | leakage | secret recovery by category |
| verbatim overlap | leakage | longest-common-substring severity score |

Inapplicable `(cell, metric)` pairs report **N/A** rather than a misleading `0.0`.

---

## Running it

**Prerequisites:** Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). No API keys — the
bundled evaluations run fully offline and deterministically.

### 1. Set up

```bash
uv venv                       # create the virtual environment
uv pip install -e '.[dev]'    # install redharness + dev/test tools
```

### 2. Run an evaluation

```bash
uv run redharness run configs/smoke.yaml             # jailbreak surface
uv run redharness run configs/injection_smoke.yaml   # prompt-injection surface
uv run redharness run configs/leakage_smoke.yaml     # data-leakage surface
```

Each run writes a folder under `runs/<run_name>/`:

| File | What it is |
|---|---|
| `report.md` | Summary table of every metric per `(attack, target)` cell |
| `report.html` | The same report as a styled, shareable page |
| `leaderboard.json` | Scored rows, each with the `(dataset_version, judge, metric)` triple |
| `transcripts.jsonl` | Full prompt/response transcript of every attempt (audit trail) |

```bash
open runs/smoke/report.html       # view a report
cat runs/smoke/leaderboard.json   # inspect the raw scored rows
```

### Other commands

```bash
uv run redharness list                          # registered plugins, grouped by axis
uv run redharness validate configs/smoke.yaml   # validate a config without running it
```

### Writing your own run

A run is a declarative YAML config naming the plugins to combine. Copy any file in
`configs/`, edit the `targets`/`attacks`/`datasets`/`judges`/`metrics` lists to other
registered names (see `redharness list`), then `validate` and `run` it.

## Using the dashboard

After one or more runs, aggregate every `runs/*/leaderboard.json` into a single page:

```bash
uv run redharness dashboard                                # reads runs/, writes dashboard.html
uv run redharness dashboard --out site/dashboard.html      # custom output path
uv run redharness dashboard --label benchmark-v1           # stamp a static release label
open dashboard.html                                        # view it (or double-click)
```

The dashboard groups results by surface (jailbreak / injection / leakage), renders a
sortable, filterable table per surface so you can compare targets per `(attack, metric)`,
and draws CSS/SVG bars for the 0–1 rate metrics (N/A cells show as `—`). It is **fully
self-contained** (no CDNs, opens from `file://`), **deterministic** (byte-identical
regeneration), and **XSS-safe** — submitted leaderboards are treated as untrusted input.

---

## Research grounding

The harness integrates prior work as first-class plugins. Full BibTeX is in
[`CITATIONS.bib`](../CITATIONS.bib). Anchors include: HarmBench and JailbreakBench
(standardized jailbreak eval + leaderboards), StrongREJECT (rigorous jailbreak scoring),
GCG / PAIR / TAP / AutoDAN (attacks), AgentDojo / InjecAgent / AgentHarm (agentic
injection), Greshake et al. (indirect injection threat model), Carlini et al. 2021 and
Nasr/Carlini 2023 (training-data extraction) and the Secret Sharer (canary memorization),
XSTest / OR-Bench (over-refusal), DecodingTrust and TrustLLM (trustworthiness), Llama
Guard / WildGuard / ShieldGemma (guardrail judges), and the OWASP LLM Top 10 + NIST AI RMF
+ MITRE ATLAS for threat framing. Tooling interop is designed for garak, PyRIT, and
Inspect.

## Status & roadmap

Implemented: the full three-surface harness, the reproducibility contract, the leaderboard
export, and the aggregating dashboard — all runnable fully offline with deterministic,
test-locked metric values.

Planned: a hosted leaderboard with a held-out, gaming-resistant submission verifier; live
model adapters (OpenAI-compatible) and bundled real attack/extraction corpora behind
explicit opt-in; and a technical report.

## Responsible use

`redharness` is a defensive evaluation tool for authorized safety testing and research. It
ships only benign, synthetic placeholder content; it does not bundle real harmful prompts,
real PII, or real memorized text. Real datasets are fetched-and-verified by hash behind an
explicit opt-in.
