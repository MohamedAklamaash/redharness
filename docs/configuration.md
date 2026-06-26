# Configuration reference

A run is described by a YAML file. `redharness run <config.yaml>` enumerates the
`Attack × Target × Dataset × Judge` (or `Injection × Target × Scenario × Judge`) matrix,
scores every cell, and writes the artifacts under `runs/<run_name>/`. Validate any config
without running it:

```bash
uv run redharness validate configs/smoke.yaml
```

## Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `run_name` | string | yes | Output folder name. Must match `^[A-Za-z0-9._-]{1,128}$` (no `/`, `..`); validated to prevent path traversal. |
| `seed` | int | no (default `0`) | Seeds deterministic execution. |
| `max_steps` | int | no (default `6`) | Injection mode only: cap on agent-loop steps (1–64). |
| `max_queries` | int | no (default unbounded) | Hard, fail-closed run-level query budget (1–10,000,000). The run aborts with a typed `RunBudgetExceeded` once exceeded — used to cap spend in live mode. |
| `targets` | list | yes | Target plugins (the systems under test). |
| `judges` | list | yes | Judge plugins (scorers). |
| `metrics` | list | yes | Metric plugins (aggregators). |
| `attacks` + `datasets` | lists | jailbreak mode | Present together for jailbreak/leakage runs. |
| `injections` + `scenarios` | lists | injection mode | Present together for prompt-injection runs. |

## Run modes

A config runs in exactly **one** mode, derived from which axes it populates (there is no
explicit `mode:` field):

- **Jailbreak / leakage mode** — populate `attacks` and `datasets`. Single-turn:
  each attack transforms each behavior and runs it against each target. The data-leakage
  surface uses this same mode with leakage attacks, the `leakage_demo` dataset, the
  `leak_detector` judge, and the leakage metrics.
- **Injection mode** — populate `injections` and `scenarios`. A deterministic tool-calling
  agent loop (bounded by `max_steps`) drives each scenario, weaving the injection into the
  user turn (direct) or a tool's output (indirect).

`targets`, `judges`, and `metrics` are shared by both modes. Populating axes from both
modes, or only half of a mode, is a validation error.

## Plugin reference forms

Each entry in an axis list is either a bare **name** or a `{name, params}` mapping. `params`
are passed as keyword arguments to the plugin's constructor.

```yaml
targets:
  - reference                  # bare name, default params
  - name: reference            # name + params
    params:
      bypass_markers: ["ignore the previous framing"]
```

Discover every registered plugin name (grouped by axis) with `uv run redharness list`.

## Worked examples

### Jailbreak

```yaml
run_name: smoke
seed: 0
targets:
  - name: reference            # strict: default broad refusal topics
    params:
      name: aligned-reference
      bypass_markers: ["ignore the previous framing"]
  - name: reference            # lenient: narrow refusal topics -> higher ASR
    params:
      name: permissive-reference
      bypass_markers: ["ignore the previous framing"]
      refusal_topics: ["ransomware", "keylogger", "botnet", "money laundering", "card skimmer", "sim swap"]
attacks: [static, template]
datasets: [demo]
judges:
  - refusal_match
  - name: rubric
    params:
      grader: {name: reference}  # LLM-as-judge grader is itself a target
metrics: [asr, asr_at_k, refusal_rate, strongreject_score, frr]
```

### Prompt injection

```yaml
run_name: injection_smoke
seed: 0
max_steps: 6
targets:
  - name: reference_agent
    params: {name: agent-aligned, susceptibility: robust}
  - name: reference_agent
    params: {name: agent-vulnerable, susceptibility: vulnerable}
injections: [no_injection, direct_injection, indirect_injection]
scenarios:
  - name: bundled
    params: {suite: injecagent_demo}
  - name: bundled
    params: {suite: agentdojo_demo}
judges: [injection_detector]
metrics: [injection_success_rate, utility_under_attack, utility_baseline]
```

### Data leakage

```yaml
run_name: leakage_smoke
seed: 0
targets:
  - name: reference_memorizer
    params: {name: reference-unaligned, policy: leaky}   # plus canaries/pii_records/system_prompt_secrets/memorized_passages
  - name: reference_memorizer
    params: {name: reference-aligned, policy: guarded}
attacks: [direct_extraction, divergence, canary_completion, system_prompt_leak, pii_elicitation]
datasets: [leakage_demo]
judges: [leak_detector]
metrics: [extraction_rate, canary_exposure_rate, pii_leak_rate, system_prompt_leak_rate, verbatim_overlap]
```

## Live evaluation

By default everything runs offline against deterministic reference targets. A first **live**
path is available behind optional extras and environment-only credentials. Read the
"Responsible use — LIVE mode" note in the [README](../README.md) first: authorized use only,
you are responsible for provider ToS, use personal not production keys, harmful outputs are
written locally (your responsibility for handling/retention), and live numbers are
single-sample / non-reproducible. A complete, commented template is in
[`configs/real_eval.example.yaml`](../configs/real_eval.example.yaml) (not run by CI).

**Install the extras** for the providers you use (both are httpx-based):

```bash
uv pip install -e '.[openai,anthropic]'
```

**Per-instance endpoint + key wiring.** Every live adapter takes its model, an optional
`base_url`, and `api_key_env` — the **name** of the environment variable holding the key.
Credentials are read only from the environment, never from YAML, so a target, a PAIR
attacker, and a grader can each point at a distinct endpoint/key:

```yaml
max_queries: 500                 # hard, fail-closed spend cap (typed abort when exceeded)
targets:
  - name: anthropic              # POST https://api.anthropic.com/v1/messages
    params:
      model: claude-opus-4-8     # x-api-key from ANTHROPIC_API_KEY (default)
      max_tokens: 1024
  - name: openai_compat          # POST {base_url}/chat/completions
    params:
      model: gpt-4o-mini
      base_url: https://api.openai.com/v1
      api_key_env: OPENAI_API_KEY
```

**PAIR (`pair`) with an injected attacker + judge.** The attack does not build its own
providers; the run builder materialises the nested `attacker` (a target spec) and `judge` (a
judge spec, with its own `grader`) before constructing the attack. `max_queries` here is a
hard per-behavior ceiling (1–200) that counts every attacker/target/judge call:

```yaml
attacks:
  - name: pair
    params:
      max_iters: 5
      n_branches: 3
      max_queries: 60
      attacker:
        name: anthropic
        params: {model: claude-sonnet-4-6, api_key_env: ANTHROPIC_ATTACKER_API_KEY}
      judge:
        name: strongreject
        params:
          grader: {name: openai_compat, params: {model: gpt-4o, base_url: https://api.openai.com/v1, api_key_env: OPENAI_GRADER_API_KEY}}
datasets:
  - name: strongreject           # 50-item subset, fetched + sha256-verified, opt-in
    params: {subset: small, allow_download: true, sha256: "<verified sha256>"}
judges:
  - name: strongreject
    params: {grader: {name: anthropic, params: {model: claude-opus-4-8, api_key_env: ANTHROPIC_GRADER_API_KEY}}}
```

## Public benchmark datasets

Beyond the bundled `demo`/`leakage_demo` sets and `strongreject`, five public
red-teaming sets plug in as fetch-by-reference loaders. **No prompts are committed**:
each is fetched from a commit-pinned URL, sha256-verified, and gated behind
`allow_download: true`. Pass the verified `sha256` (the committed default is a
placeholder that fails closed). Forbidden-prompt sets map to `should_refuse`; the
over-refusal sets map benign prompts to `should_comply` so the false-refusal-rate
(`frr`) metric is exercised.

| Dataset name | Source | Maps to | Use |
|---|---|---|---|
| `advbench` | llm-attacks/llm-attacks | `should_refuse` | harmful behaviors (ASR) |
| `harmbench` | centerforaisafety/HarmBench | `should_refuse` | standard behaviors (ASR) |
| `jbb_behaviors` | JailbreakBench/jailbreakbench | `should_refuse` | JBB harmful set (ASR) |
| `xstest` | paul-rottger/xstest | `should_comply` (safe split) / `should_refuse` (contrast) | exaggerated safety (FRR) |
| `or_bench` | OR-Bench | `should_comply` | over-refusal (FRR) |

```yaml
datasets:
  - name: advbench
    params: {allow_download: true, limit: 50, sha256: "<verified sha256>"}
  - name: xstest
    params: {allow_download: true, sha256: "<verified sha256>"}
```

See `CONTRIBUTING.md` for the per-dataset source-URL / license / fetch-not-redistribute
table.

## Cost & token-usage metrics

Two metrics report what a **live** run consumed, read from the per-behavior token
totals the runner stamps at its single budget choke point:

| Metric | Reports |
|---|---|
| `token_usage` | total input + output tokens across behaviors (with a breakdown). |
| `cost` | estimated USD from a small, dated price table (`metrics/cost.py`), matched by model id. |

Both group **by behavior** (counted once, like ASR), ignore failed/retried calls that
carry no `usage`, and never double-count cache hits. Both return **N/A** (`—` /
`null`) for offline/reference runs (no provider was queried) — and `cost` is also N/A
when no behavior's model is in the price table, so a local-model run reports `—`
rather than a misleading `$0`. Tokens are the primary signal; dollars are an estimate
only — verify against your provider's current pricing.

```yaml
metrics: [asr, refusal_rate, token_usage, cost]
```

## Tool calling (live targets)

The `openai_compat` and `anthropic` targets serialize a `tools=` argument into the
provider request and parse the provider's native tool-call shape (OpenAI
`message.tool_calls[].function`, Anthropic `tool_use` content blocks) back into the
normalized `[{name, arguments, call_id}]` list the injection agent loop consumes. No
config is needed — wiring a live target into an injection-mode run now exercises real
tool calls instead of silently ignoring the tool schema.

## Local servers (Ollama / vLLM)

A self-hosted OpenAI-compatible server is just the `openai_compat` target pointed at a
loopback `base_url` (already permitted without TLS) — there is no separate adapter:

```yaml
targets:
  - name: openai_compat            # Ollama:  ollama serve  (OpenAI API at :11434/v1)
    params: {model: llama3.1, base_url: http://localhost:11434/v1, api_key_env: OLLAMA_API_KEY}
  - name: openai_compat            # vLLM:    vllm serve <model>  (OpenAI API at :8000/v1)
    params: {model: mistralai/Mistral-7B-Instruct-v0.3, base_url: http://localhost:8000/v1, api_key_env: VLLM_API_KEY}
```

Most local servers ignore the key, but the adapter still reads a (possibly dummy)
value from `api_key_env`. A complete template is in
[`configs/local_servers.example.yaml`](../configs/local_servers.example.yaml).

## Outputs

Each run writes to `runs/<run_name>/`:

| File | Contents |
|---|---|
| `report.md` / `report.html` | Per-`(attack, target)` metric tables. |
| `leaderboard.json` | One row per `(attack, target, dataset, judge, metric)`, each carrying the `(dataset_version, judge, metric)` provenance triple. N/A values are `null`. |
| `transcripts.jsonl` | The full transcript of every attempt (the audit trail). |

Launch the optional Streamlit leaderboard over all runs with `uv pip install -e '.[dashboard]'`
then `uv run redharness dashboard`. See [`OVERVIEW.md`](OVERVIEW.md) for the dashboard, and
[`extending.md`](extending.md) to add your own plugins.
