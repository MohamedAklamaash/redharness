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
  - mock                       # bare name, default params
  - name: mock                 # name + params
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
  - name: mock
    params:
      bypass_markers: ["ignore the previous framing"]
attacks: [static, template]
datasets: [demo]
judges:
  - refusal_match
  - name: rubric
    params:
      grader: {name: mock}     # LLM-as-judge grader is itself a target
metrics: [asr, asr_at_k, refusal_rate, strongreject_score, frr]
```

### Prompt injection

```yaml
run_name: injection_smoke
seed: 0
max_steps: 6
targets:
  - name: mock_agent
    params: {name: agent_robust, susceptibility: robust}
  - name: mock_agent
    params: {name: agent_vulnerable, susceptibility: vulnerable}
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
  - name: leaky_mock
    params: {name: model_leaky, policy: leaky}
  - name: leaky_mock
    params: {name: model_guarded, policy: guarded}
attacks: [direct_extraction, divergence, canary_completion, system_prompt_leak, pii_elicitation]
datasets: [leakage_demo]
judges: [leak_detector]
metrics: [extraction_rate, canary_exposure_rate, pii_leak_rate, system_prompt_leak_rate, verbatim_overlap]
```

## Outputs

Each run writes to `runs/<run_name>/`:

| File | Contents |
|---|---|
| `report.md` / `report.html` | Per-`(attack, target)` metric tables. |
| `leaderboard.json` | One row per `(attack, target, dataset, judge, metric)`, each carrying the `(dataset_version, judge, metric)` provenance triple. N/A values are `null`. |
| `transcripts.jsonl` | The full transcript of every attempt (the audit trail). |

Aggregate all runs into a single offline page with `uv run redharness dashboard`. See
[`OVERVIEW.md`](OVERVIEW.md) for the dashboard, and [`extending.md`](extending.md) to add
your own plugins.
