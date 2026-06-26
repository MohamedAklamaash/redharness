# Using the published `redharness` package

`redharness` is published on PyPI: <https://pypi.org/project/redharness/>. This guide is for
people who want to **install and use the released package** without cloning the repository —
the CLI, the bundled offline datasets, live evaluation, the dashboard, and the Python API.

If you have cloned the repo and want the editable-install workflow with the example configs,
read [OVERVIEW.md](OVERVIEW.md) instead; for the full YAML schema see
[configuration.md](configuration.md); to add your own plugins see [extending.md](extending.md).

---

## 1. Install

The core package is offline and deterministic (only `pydantic`, `pyyaml`, `jinja2`, `typer`):

```bash
pip install redharness
```

Heavier capabilities ship as **optional extras**, so the base install stays lean. Combine the
ones you need:

| Extra | `pip install` | Adds |
|---|---|---|
| `openai` | `redharness[openai]` | the `openai_compat` live adapter (OpenAI / Ollama / vLLM / any OpenAI-compatible endpoint) |
| `anthropic` | `redharness[anthropic]` | the `anthropic` live adapter |
| `dashboard` | `redharness[dashboard]` | the Streamlit leaderboard dashboard |
| `hf` | `redharness[hf]` | the local Hugging Face classifier judge (`hf_classifier`) |
| `gcg` / `garak` / `pyrit` | `redharness[gcg]` … | external-attack scaffolds (heavy deps) |

```bash
# A typical live-evaluation install:
pip install "redharness[openai,anthropic,dashboard]"
```

`uv`, `pipx`, and `poetry` work the same way (`uv pip install redharness`,
`pipx install redharness`). Requires Python 3.11+.

Verify the install — the package exposes a console command, `redharness`:

```bash
redharness --help
redharness list          # every registered plugin, grouped by axis
python -c "import redharness; print(redharness.__version__)"   # 0.1.0
```

---

## 2. What ships in the wheel (and what doesn't)

The installed package contains the **runner, every plugin, and the bundled synthetic
datasets** — so the offline evaluations run with zero setup and no network. It does **not**
ship the repository's `configs/` example files. You author your own YAML config (a few lines —
see below) or copy one from the
[`configs/` directory on GitHub](https://github.com/MohamedAklamaash/redharness/tree/main/configs).

Bundled, ready-to-reference offline data: the `demo` jailbreak behaviors and the
`leakage_demo` probe set, plus the `reference` / `reference_agent` / `reference_memorizer`
deterministic target models. The opt-in real datasets (`advbench`, `harmbench`,
`jbb_behaviors`, `xstest`, `or_bench`, `strongreject`) are fetched-and-verified by hash at
runtime — no corpora are committed or shipped.

---

## 3. Run an offline evaluation (no keys, no network)

Write a minimal config that combines bundled plugins. This one runs the jailbreak surface
against the two reference targets end-to-end:

```yaml
# my_smoke.yaml
run_name: my_smoke
seed: 0

targets:
  - name: reference
    params: { name: aligned-reference }
  - name: reference
    params: { name: permissive-reference }

attacks:
  - static
  - template

datasets:
  - demo

judges:
  - refusal_match
  - name: rubric
    params:
      grader: { name: reference }

metrics:
  - asr
  - refusal_rate
  - strongreject_score
  - frr
```

```bash
redharness validate my_smoke.yaml     # check it without running
redharness run my_smoke.yaml          # execute; writes to ./runs/my_smoke/
```

Every run writes a folder under `runs/<run_name>/`:

| File | What it is |
|---|---|
| `report.md` | Summary table of every metric per `(attack, target)` cell |
| `report.html` | The same report as a styled, shareable page |
| `leaderboard.json` | Scored rows, each carrying the `(dataset_version, judge, metric)` triple |
| `transcripts.jsonl` | Full prompt/response transcript of every attempt (audit trail) |

```bash
open runs/my_smoke/report.html
cat runs/my_smoke/leaderboard.json
```

Useful flags: `--runs-dir <dir>` (where artifacts land), `--concurrency N` (bounded worker
threads), `--trials N` (repeat under N seeds and report mean + confidence interval).

The injection and leakage surfaces work the same way — set `mode: injection` (with
`injections`/`scenarios` axes) or use the leakage plugins (`leakage_demo` dataset,
`leak_detector` judge, `direct_extraction`/`canary_completion`/`pii_elicitation`/
`system_prompt_leak` attacks). See [configuration.md](configuration.md) for the full schema.

---

## 4. Evaluate a real model (your keys, your cost)

Install a provider extra, export the credential as an environment variable (keys are read
**only** from the environment — never put them in YAML), then point a target at it.

```bash
pip install "redharness[anthropic]"
export ANTHROPIC_API_KEY=sk-ant-...
```

```yaml
# real.yaml — Anthropic target on the StrongREJECT set, capped spend
run_name: real_eval
seed: 0

targets:
  - name: anthropic
    params:
      model: claude-haiku-4-5
      max_queries: 50        # fail-closed budget: counts real HTTP calls

attacks:
  - static

datasets:
  - strongreject            # fetched + hash-verified on first use

judges:
  - refusal_match
  - name: strongreject
    params:
      grader:
        name: anthropic
        params: { model: claude-haiku-4-5 }

metrics:
  - asr
  - strongreject_score
  - token_usage
  - cost
```

```bash
redharness run real.yaml
```

For an OpenAI-compatible or local endpoint, use the `openai_compat` target
(`base_url` + the env var holding the key; a local Ollama/vLLM server needs no real key).
The full live-evaluation runbook — provider extras, dataset pinning, the `max_queries`
budget, tool-calling for the injection surface, and a **Troubleshooting** section (including
the macOS `CERTIFICATE_VERIFY_FAILED` fix you may hit on the first real fetch) — is in
[configuration.md](configuration.md).

> **Responsible use.** Live mode is for authorized testing only. You own each provider's
> Terms of Service, should use personal/research keys, and own the handling of any harmful
> outputs written under `runs/`. Live numbers are single-sample and non-reproducible — cap
> spend with `max_queries`.

---

## 5. Launch the dashboard

The leaderboard dashboard is a Streamlit app shipped behind the `dashboard` extra:

```bash
pip install "redharness[dashboard]"
redharness dashboard                              # http://localhost:8501 over ./runs
redharness dashboard --runs-dir runs --port 8502  # custom runs dir / port
```

It reads every `runs/*/leaderboard.json`, groups rows by surface, and gives you filters and a
per-surface sortable table + bar chart. If the extra is missing, the command prints an install
hint and exits non-zero.

---

## 6. Use it as a Python library

The same path the CLI takes is importable. Load a config, run it, and write the reports:

```python
import redharness.plugins                       # populates the registry (built-in plugins)
from pathlib import Path
from redharness.config import load_config
from redharness.runner import Runner
from redharness.report import write_reports

cfg = load_config("my_smoke.yaml")
runner = Runner(cfg, Path("runs"))
result = runner.run()
paths = write_reports(result, runner.run_dir)

print(f"{len(result.cells)} cells -> {paths['leaderboard']}")
```

Inspect what's registered without running anything (`import redharness.plugins` first — plugins
self-register at import time):

```python
import redharness.plugins
from redharness.core.registry import registry   # typed name -> plugin registry

print(registry.targets.names())   # ['anthropic', 'openai_compat', 'reference', ...]
print(registry.attacks.names())
print(list(registry.by_axis()))   # every axis: targets, attacks, datasets, judges, ...
```

To register **your own** Target/Attack/Dataset/Judge/Metric against the installed package,
import `redharness` so the built-ins load, then apply the plugin decorators shown in
[extending.md](extending.md) — your plugin becomes referenceable by name from YAML just like
the built-ins.

---

## 7. Upgrading

```bash
pip install -U redharness
redharness list      # confirm the plugin surface after upgrading
```

Releases are tagged on GitHub with a `CHANGELOG.md` entry; the version is also exposed as
`redharness.__version__`.
