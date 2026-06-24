# redharness

### A standardized, reproducible benchmark for adversarial evaluation of large language models across jailbreak, prompt-injection, and data-leakage threat surfaces

`redharness` is an open-source evaluation framework for measuring the adversarial
robustness and safety of large language models (LLMs). It unifies three threat surfaces
that are today measured inconsistently and incomparably — **jailbreaks**, **prompt
injection**, and **data leakage** — under a single pluggable methodology with a strict
reproducibility contract and per-result provenance.

> **Hands-on usage** (installation, running evaluations, reading outputs, launching and
> using the leaderboard dashboard, writing your own configs) lives in
> [`docs/OVERVIEW.md`](docs/OVERVIEW.md). This README documents *what* the benchmark is,
> *why* it exists, and *who* it is for.

---

## Abstract

Adversarial evaluation of LLMs has advanced rapidly, but its empirical foundations are
fragile. Each attack paper tends to ship a bespoke evaluation harness, an idiosyncratic
notion of "Attack Success Rate," and a judge whose behavior is rarely held fixed across
studies — so reported numbers are frequently not comparable across papers, and in several
cases have been shown to *overestimate* true attack success [Souly et al. 2024]. The
benchmarks that achieved durable community adoption (HarmBench [Mazeika et al. 2024],
JailbreakBench [Chao et al. 2024]) did so primarily by *standardizing the evaluation* —
fixed behaviors, fixed judges, versioned artifacts, public leaderboards — rather than by
introducing the strongest individual attack. `redharness` generalizes that insight into a
single harness spanning three surfaces, with hash-pinned datasets, deterministic seeded
execution, persisted transcripts, and a `(dataset_version, judge, metric)` provenance
triple recorded for every reported number. The same standardization is extended to the
prompt-injection and data-leakage surfaces, which remain comparatively unstandardized
despite prompt injection ranking first on the OWASP Top 10 for LLM Applications for two
consecutive years.

## 1. Motivation

Three structural problems make current LLM-safety results hard to trust and harder to
compare:

1. **Metric incommensurability.** "ASR" denotes different quantities across papers (any
   successful attempt vs. success within a query budget vs. a judge's continuous score),
   computed over different behavior sets. Headline numbers therefore cannot be compared
   directly.
2. **Judge sensitivity.** Whether a response is "harmful," a successful "injection," or a
   "leak" depends heavily on the grader. Souly et al. [2024] demonstrate that weak or
   permissive judges systematically inflate jailbreak success; small changes in the judge
   move headline numbers by tens of points.
3. **Irreproducibility.** Datasets drift or are unversioned, random seeds and decoding
   parameters go unlogged, transcripts are discarded, and public leaderboards are
   vulnerable to overfitting and gaming.

The downstream consequence is that a practitioner cannot reliably answer the basic
question *"Is model A safer than model B, by how much, under which threat model — and can
anyone reproduce that number?"* `redharness` is designed so that this question has a
reproducible, provenance-tracked answer.

## 2. Contributions

- **A unified, pluggable methodology across three surfaces.** A single
  `Attack × Target × Dataset × Judge × Metric` matrix (extended with `Scenario` and
  `Injection` axes for agentic injection) spans jailbreak, prompt-injection, and
  data-leakage evaluation, so the three surfaces share one vocabulary, one runner, and one
  reporting format.
- **Standardization of the under-standardized surfaces.** Injection and leakage are given
  the same first-class, versioned, judge-explicit treatment that HarmBench/JailbreakBench
  brought to jailbreaks.
- **A reproducibility contract.** Hash-pinned datasets, deterministic seeded execution,
  parameter-aware result caching, and persisted JSONL transcripts make a leaderboard row
  reproducible from a single command.
- **Per-result provenance.** Every leaderboard entry records the
  `(dataset_version, judge, metric)` triple, eliminating the ambiguity that drives metric
  incommensurability.
- **Designed for interoperability, not re-implementation.** Accepted datasets and judges
  are integrated as plugins so results align with published work; established tooling
  (garak, PyRIT, Inspect) attaches through documented extension seams rather than forks.
- **A gaming-aware leaderboard dashboard** — an optional Streamlit web app that aggregates
  all runs into a filterable, per-surface view and treats submitted results as untrusted input.

## 3. Background and related work

**Standardization frameworks and leaderboards.** HarmBench [Mazeika et al. 2024,
arXiv:2402.04249] introduced a standardized automated red-teaming evaluation and a
fine-tuned harmful-behavior classifier that became a de-facto judge. JailbreakBench [Chao
et al. 2024, arXiv:2404.01318] added an open robustness benchmark with a public leaderboard
and versioned artifacts. StrongREJECT [Souly et al. 2024, arXiv:2402.10260] showed that
prior benchmarks overestimate attack success and contributed a high-agreement rubric grader.
DecodingTrust [Wang et al. 2023, arXiv:2306.11698] and TrustLLM [Sun et al. 2024,
arXiv:2401.05561] provide multi-perspective trustworthiness evaluation; HELM Safety
[Stanford CRFM 2024] aggregates safety benchmarks under a common interface.

**Jailbreak attacks.** GCG [Zou et al. 2023, arXiv:2307.15043] established transferable
gradient-based adversarial suffixes (and the AdvBench behavior set); PAIR [Chao et al. 2023,
arXiv:2310.08419] and TAP [Mehrotra et al. 2023, arXiv:2312.02119] are query-efficient
black-box attacker-LLM methods; AutoDAN [Liu et al. 2023, arXiv:2310.04451] evolves fluent,
stealthy prompts.

**Prompt injection.** Greshake et al. [2023, arXiv:2302.12173] formalized indirect prompt
injection against LLM-integrated applications. AgentDojo [Debenedetti et al. 2024,
arXiv:2406.13352], InjecAgent [Zhan et al. 2024, arXiv:2403.02691], and AgentHarm
[Andriushchenko et al. 2024, arXiv:2410.09024] define the agentic attack surface; the OWASP
Top 10 for LLM Applications ranks prompt injection first.

**Data leakage and memorization.** Carlini et al. [2021, arXiv:2012.07805] extract training
data from LLMs; Nasr, Carlini et al. [2023, arXiv:2311.17035] scale extraction to production
models via divergence attacks; the Secret Sharer [Carlini et al. 2019, arXiv:1802.08232]
introduces canary-based memorization measurement, which `redharness` adopts for its leakage
scoring.

**Over-refusal.** XSTest [Röttger et al. 2024, arXiv:2308.01263] and OR-Bench [Cui et al.
2024, arXiv:2405.20947] measure false refusals on benign prompts, so safety can be reported
against the helpfulness it trades against rather than in isolation.

**Guardrail judges and tooling.** Llama Guard [Inan et al. 2023, arXiv:2312.06674], WildGuard
[Han et al. 2024], and ShieldGemma [Zeng et al. 2024] are pluggable safety classifiers;
garak (NVIDIA), PyRIT (Microsoft), and Inspect (UK AISI) are established red-teaming and
evaluation toolkits. Governance framing follows the NIST AI Risk Management Framework and
MITRE ATLAS. Full BibTeX is provided in [`CITATIONS.bib`](CITATIONS.bib).

## 4. Threat model

`redharness` standardizes evaluation across the three surfaces that are least consistently
measured today.

**(S1) Jailbreaks.** An adversary manipulates a prompt to elicit content the model is
intended to refuse. Evaluation balances attack success against over-refusal, so that a
trivially refusing model is not mistaken for a safe one.

**(S2) Prompt injection (direct and indirect/agentic).** An adversary smuggles instructions
into a tool-using agent — placed directly in the user turn, or *indirectly* in a document or
tool output the agent consumes — to make it pursue an attacker-chosen goal. Evaluation
measures both whether the attacker's goal fired and whether the agent still completed its
legitimate task (utility under attack).

**(S3) Data leakage.** An adversary recovers memorized or secret content: training-data
extraction and divergence, canary recovery, PII elicitation, and system-prompt
exfiltration. Evaluation reports both a binary recovery decision and a continuous
verbatim-overlap severity score.

All bundled artifacts are synthetic and benign — placeholder behaviors, benign *sentinel*
attacker goals, and obviously-fake secrets (e.g. `*.example.invalid` PII) — so the harness
mechanics can be exercised without distributing harmful prompts, real PII, or memorized
text. Real corpora attach behind explicit, hash-verified opt-in (§9, §11).

## 5. Methodology

Every evaluation is a matrix over five plugin axes; a run enumerates the cells and scores
each one:

```
 Dataset ─▶ Attack ─▶ Target ─▶ transcript ─▶ Judge ─▶ Metric ─▶ Report / Leaderboard ─▶ Dashboard
(behaviors) (generator) (model)               (scorer) (aggregate)
```

| Axis | Role | Interface |
|---|---|---|
| **Target** | the system under test | `generate(messages, tools) -> Response` |
| **Attack** | transforms a behavior into one or more adversarial attempts | `run(behavior, target) -> list[Attempt]` |
| **Dataset** | a versioned, hash-pinned set of behaviors/probes | `load() -> list[Behavior]` |
| **Judge** | decides success and assigns a score per attempt | `score(behavior, attempt) -> Verdict` |
| **Metric** | aggregates verdicts into a reported quantity | `compute(scored) -> MetricResult` |

The agentic prompt-injection surface adds two axes — **Scenario** (a sandboxed tool
environment with a benign user task and a benign attacker goal) and **Injection** (the
malicious instruction and its placement) — driven by a bounded multi-step agent loop. The
data-leakage surface is single-turn and reuses the jailbreak execution path with
leakage-specific plugins, so no separate runner mode is required.

**Reproducibility contract.** Datasets are content-addressed (hash-pinned) and verified
before use; execution is deterministically seeded; attempts are cached on their fully
resolved parameters (so a parameter change never silently reuses a stale result); and the
complete prompt/response transcript of every attempt is persisted as JSONL for audit. A
single command reproduces a leaderboard row.

**Provenance.** Each leaderboard entry records the `(dataset_version, judge, metric)`
triple. Because judge choice and dataset version are the dominant sources of cross-study
disagreement, binding them to every number is the framework's central anti-fragmentation
mechanism.

**Extensibility.** Plugins self-register and are resolved by name from declarative YAML
through a closed registry (a dictionary lookup — never dynamic import or `eval` — so a
configuration cannot execute arbitrary code). Adding an attack, model adapter, judge,
dataset, or metric is a small, self-contained addition; network-heavy frameworks (PAIR,
TAP, garak, PyRIT) and real corpora attach behind dependency extras so the offline core
stays lean. The concrete "add a plugin" walkthrough is in [`docs/OVERVIEW.md`](docs/OVERVIEW.md).

## 6. Metrics

All metrics are defined as pure functions over scored attempts; inapplicable
`(cell, metric)` pairs report **N/A** rather than a misleading `0.0`.

| Metric | Definition | Grounding |
|---|---|---|
| `asr` | fraction of harmful behaviors with ≥ 1 successful attempt | HarmBench / JailbreakBench |
| `asr_at_k` | success within the first *k* attempts (query budget) | PAIR / TAP |
| `strongreject_score` | `0` if refused, else the 1–5 mean of *specificity*/*convincingness* rescaled to [0,1] as `(mean−1)/4` | StrongREJECT |
| `refusal_rate` | fraction of harmful behaviors refused on every attempt | DecodingTrust |
| `frr` | false-refusal rate over the benign should-comply subset | XSTest / OR-Bench |
| `injection_success_rate` | fraction of *injected* scenarios in which the attacker goal fired | InjecAgent / AgentDojo |
| `utility_under_attack` | fraction of *injected* scenarios in which the benign task still completed | AgentDojo |
| `utility_baseline` | benign-task completion with no injection (control) | AgentDojo |
| `extraction_rate` | overall fraction of probes whose synthetic secret leaked | Carlini 2021 / Nasr 2023 |
| `canary_exposure_rate` | leak rate over canary probes | Secret Sharer (Carlini 2019) |
| `pii_leak_rate` | leak rate over PII probes | DecodingTrust |
| `system_prompt_leak_rate` | leak rate over system-prompt probes | — |
| `verbatim_overlap` | mean best verbatim overlap (longest-common-substring ratio) | Carlini 2021 / Nasr 2023 |

## 7. Who should use redharness, and why

- **Safety and alignment researchers** — to report jailbreak/injection/leakage results that
  are directly comparable to prior work, with the judge and dataset version pinned to every
  number, and to study judge sensitivity by re-scoring the same transcripts under different
  graders.
- **Model developers and labs** — to track adversarial robustness across model versions as a
  reproducible regression suite, balancing attack resistance against over-refusal so safety
  gains are not just refusal gains.
- **Red teams and AI security engineers** — to evaluate agentic systems against direct and
  indirect prompt injection and to quantify utility under attack, mapping to the OWASP LLM
  Top 10 and MITRE ATLAS.
- **Auditors, evaluators, and policymakers** — to obtain provenance-tracked, reproducible
  evidence aligned with the NIST AI RMF for governance and procurement decisions.
- **Educators and students** — to study attack and defense mechanisms hands-on, entirely
  offline, against deterministic targets and benign synthetic data.

## 8. Reproducibility and artifacts

The harness is deterministic and fully offline by default — no API keys are required for the
bundled evaluations, and results are identical across machines and runs. Each run emits a
Markdown and HTML report, a machine-readable `leaderboard.json` (with the provenance triple
on every row), and a complete JSONL transcript. The optional `redharness dashboard` command
launches a Streamlit web app that aggregates every run into a filterable, per-surface
leaderboard. The literature the framework is grounded in is enumerated in
[`CITATIONS.bib`](CITATIONS.bib).

## 9. Limitations and current scope

The framework and the offline evaluation paths for all three surfaces are implemented and
test-locked. Currently scaffolded behind clean interfaces and explicit opt-in (not yet
wired): live model adapters (OpenAI-compatible endpoints) and bundled real attack/extraction
corpora (e.g. AgentDojo/InjecAgent attack sets, web-scale divergence prompts). The bundled
content is intentionally synthetic, so absolute numbers from the smoke evaluations are
illustrative of the *mechanism*, not of any real model's safety. A hosted leaderboard with a
held-out, gaming-resistant submission verifier, and a technical report, are planned.

## 10. Responsible use

`redharness` is a defensive evaluation tool intended for authorized safety testing and
research. It ships only benign, synthetic placeholder content; it does not distribute real
harmful prompts, real PII, or real memorized text. Real datasets are fetched from their
canonical sources and verified by hash behind an explicit opt-in. Use it to measure and
improve model safety.

## 11. Getting started

See [`docs/OVERVIEW.md`](docs/OVERVIEW.md) for installation, running evaluations across the
three surfaces, interpreting the outputs, generating and using the leaderboard dashboard,
and writing your own run configurations.

## Citing

If you use `redharness` in academic work, please cite this repository and the upstream
benchmarks and methods it integrates (see [`CITATIONS.bib`](CITATIONS.bib)).

```bibtex
@software{redharness,
  title  = {redharness: A Standardized, Reproducible Benchmark for Adversarial
            Evaluation of Large Language Models},
  author = {Mohamed Aklamaash},
  year   = {2026},
  note   = {Jailbreak, prompt-injection, and data-leakage evaluation harness},
  url    = {https://github.com/MohamedAklamaash/redharness}
}
```

## License

Apache-2.0.
