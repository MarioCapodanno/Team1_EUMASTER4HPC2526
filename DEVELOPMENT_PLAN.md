# Development Plan (Jan–Mar 2026)
> AI Factory Benchmarking Framework (Team 1) — **engineer-grade benchmarks** with **CLI + Web GUI** parity.
> 
> **Core Philosophy**: Ultra user-friendly, highly convenient for AI factory engineers — "run one command, get actionable insights."
> 
> **Service Strategy**: Cover all challenge categories with a practical, engineer-useful suite:
> - **Inference**: vLLM, Ollama, **(optional) Triton**
> - **Storage**: PostgreSQL, **(new) MinIO**, **(new) Redis**
> - **Retrieval**: ChromaDB, **(new) Qdrant**
>
> **Implementation Strategy (Low-Friction Order)**:
> 1) First make the data/UX pipeline solid (artifacts → metrics → report → GUI) using existing services  
> 2) Then add new services in an order that minimizes dependencies and HPC friction  
> 3) Only after core stability, add optional real-time monitoring (Prometheus/Grafana)

## 🎯 Implementation Status (Current Session Completed)

### ✅ Plan Refinements Completed (2026-01-07)
The development plan has been finalized and is now ready for AI agent execution. The following alignment and refinement tasks were completed:

1. **Evaluation Checklist Added**: Mapped challenge grading criteria (experiments evidence, metrics collection, design parameters, analysis, reproducibility) to concrete deliverables with acceptance criteria.

2. **Killer Features Defined**: Added 5 differentiating features (KF1-KF5) that position the framework as "engineer-grade" rather than just "monitoring dashboards":
   - KF1: Automated Saturation Finder (knee detection for SLO-based recommendations)
   - KF2: Bottleneck Attribution (compute/memory/I/O/queueing analysis with actionable next steps)
   - KF3: Reproducibility Bundle (complete rerun capability from stored metadata)
   - KF4: Drift & Regression Detection (baseline vs current comparison with PASS/FAIL gates)
   - KF5: Engineer "One Page" Summary (decision-oriented metrics in reports)

3. **Optional Prometheus/Grafana Track**: Added as an optional add-on (disabled by default) to satisfy "checkbox compliance" without derailing core artifact-based approach.

4. **Challenge Architecture Alignment**: Explicit mapping of Servers/Clients/Monitors/Logs/Interface module requirements to concrete CLI + GUI features with "preserve vs extend" implementation notes.

5. **CLI Flag Audit**: Scanned `src/frontend.py` and documented existing flags to prevent duplicates:
   - Already implemented: `--ui`, `--list`, `--summary`, `--watch`, `--logs`, `--metrics`, `--stop`, `--web`, `--id`
   - Missing (to be added): `--report`, `--compare`, optional `--rerun`, `--download-logs`, `--list-recipes`

6. **Web UI Clarification**: Confirmed `--web` launches a Flask-based interface (not Streamlit/Gradio); updated help text and documentation accordingly.

7. **README.md Updated**: Corrected quick start guide and usage examples to match actual implementation.

### Next Steps for AI Agent
The plan is now ready for execution. The agent should:
- Start with M0 baseline check
- Follow Week 1-4 tasks in Month 2 (artifact standardization → reporting → GUI → integration)
- Preserve all working code (explicit "preserve vs extend" list provided)
- Implement at minimum KF1, KF4, KF5 during Month 2 Week 4

---

## User Experience Philosophy (ULTRA USER-FRIENDLY)

The framework must be **effortless to use** while producing **production-quality outputs**. This is our primary differentiation from other teams.

### UX Principles (Must Follow)

**1. One-Command Benchmark**
- User runs: `python src/frontend.py examples/recipe_vllm.yaml`
- Everything happens automatically: deploy → wait for healthy → run clients → collect metrics → generate report
- No manual steps required between service start and results

**2. Smart Defaults + Full Customization**
- Every recipe has sensible defaults (partition, time limits, warmup delays)
- Power users can override everything in the recipe
- Service type auto-configures: image, port, environment, health endpoint

**3. Instant Feedback**
- CLI shows progress: "Deploying service... ✓", "Waiting for health... ✓", "Running clients..."
- `--watch` shows live status without manual polling
- Web UI auto-refreshes benchmark status

**4. Self-Documenting Results**
- Every benchmark produces a report that explains itself
- Methodology section: "what we measured and how"
- Reproducibility section: "how to rerun this exact experiment"

**5. Error Recovery & Guidance**
- If service fails health check: show what went wrong + suggest fixes
- If clients fail: partial results still saved, report indicates failures
- `--stop` cleanly cancels everything for a benchmark

### Borrowed Ideas (From Other Teams, Made Better)

**From Team 8 (monitoring):**
- Health check endpoints per service type ✓ (we have this)
- Per-service metrics definitions → **we will add service-specific metrics documentation**

**From Team 9 (web experience):**
- Web-based log browser → **we have this in Flask UI**
- SSH tunnel guidance → **we will document in operations.md**

**From Team 10 (session management):**
- Complete session lifecycle → **we have --stop, need --download-logs**
- Results download to local machine → **add this feature**

**Our unique additions (no other team has):**
- Saturation finder (KF1)
- Bottleneck attribution (KF2)
- Regression detection (KF4)
- One-page engineer summary (KF5)

---

## Killer Features (Differentiators to Win)
These are features that make the framework *more valuable to cluster engineers* than a typical “deploy + measure + Grafana” project.

### KF1 — Automated Saturation Finder (knee detection)
For a concurrency sweep, automatically detect the “knee” where tail latency (P95/P99) grows sharply and throughput stops scaling.
- Output: recommended max concurrency under a user-defined SLO (e.g., `p99_latency_ms <= 1000`).
- Evidence: plot + report section “Saturation Point & Recommended Operating Range”.

### KF2 — Bottleneck Attribution (compute vs memory vs I/O vs queueing)
Use collected metrics (Slurm job stats + GPU snapshots + request latency distribution) to generate *a hypothesis-backed* bottleneck classification:
- GPU-bound (high GPU util, stable CPU, rising TTFT/latency)
- CPU-bound (high CPU time / high RSS + low GPU util)
- Memory-bound (high RSS, rising latency, possible OOM/evictions)
- Service queueing / overload (throughput saturates, p99 explodes, error rate rises)
- Network/IO suspicion (latency spikes without compute saturation; if available: I/O counters)

Deliver in report as:
- “Most likely bottleneck: …”
- “Supporting evidence: …”
- “Next tuning actions: …”

### KF3 — Reproducibility Bundle (one-command rerun)
For every benchmark ID, provide a complete rerun bundle:
- `results/<id>/run.json` contains exact recipe + slurm parameters + container image string + node list + git commit
- `python src/frontend.py --rerun <id>` (or documented equivalent) re-executes the same experiment
- Evidence: rerun produces a new benchmark ID with comparable results, recorded in dataset index

### KF4 — Drift & Regression Detection
Enable comparison of a “baseline” vs “current” run:
- detect regressions in p99 latency, throughput, and error rate
- output a PASS/FAIL gate in CLI and report (useful for system upgrades / driver changes)
- Evidence: `--compare` prints deltas and flags regressions beyond thresholds

### KF5 — Engineer-Friendly Summary (“One Page” report)
Every report begins with a short decision-oriented summary:
- “Max sustainable concurrency under SLO”
- “Peak throughput achieved”
- “Tail latency at peak”
- “Resource efficiency” (e.g., requests/sec per GPU or TPS per CPU-hour)
- “Top issues encountered” (errors, timeouts, OOM)

These KF items are designed to be implemented with the existing artifact-based pipeline (JSONL → summary/report/plots) and do not require heavy monitoring infrastructure.

## Evaluation Checklist (Aligned with Challenge Grading Criteria)
This section is the **grading-aligned checklist**. For each item, the project must produce concrete evidence in the repository (artifacts, logs, reports, screenshots).

**Extra win condition (recommended):**
- At least one experiment demonstrates **KF1 Saturation Finder** and **KF2 Bottleneck Attribution** in the generated report and plots.

### 1) Evidence of executed experiments on MeluXina
**Goal:** prove you actually ran experiments on the target HPC.

Evidence to provide (must):
- A **demo video** (link in `README.md` or `docs/demo.md`).
- **Logs** from real runs:
  - Slurm output/error logs for service and clients
  - Orchestrator logs (CLI output) saved/captured
- A minimal “Experiment Index”:
  - `docs/dataset_index.md` mapping benchmark IDs → recipe → date/time → purpose

Acceptance criteria:
- At least **one inference run** (vLLM or Ollama) and **one storage run** (PostgreSQL) executed on MeluXina.
- Benchmark IDs in `docs/dataset_index.md` correspond to existing `results/<id>/` and `reports/<id>/` artifacts.

### 2) Collect metrics from experiments
**Goal:** collect both generic hardware usage and workload-specific metrics.

Evidence to provide (must):
- Hardware usage metrics:
  - Slurm `sacct` metrics per job (CPUTime, MaxRSS/AveRSS, elapsed, node list)
  - GPU snapshot metrics via `nvidia-smi` where applicable (utilization %, memory used/total)
- Server/workload-specific metrics:
  - LLM inference: tokens/sec (if available), requests/sec, latency percentiles (P50/P95/P99), error rate
  - Storage: TPS/QPS, latency percentiles, error rate

Acceptance criteria:
- `results/<id>/summary.json` exists and contains:
  - latency percentiles (P50/P95/P99 at minimum)
  - throughput (RPS and/or TPS)
  - success rate
- GUI “Metrics” view displays the same values (table + plot) for the benchmark.

### 3) Experimental design parameters
**Goal:** show you designed experiments intentionally and can scale/compare.

Evidence to provide (must):
- Slurm configuration captured per run:
  - nodes, partition, time limit, account, resources (CPU/GPU/mem) from recipe
  - actual node allocation from Slurm (hostname/nodelist)
- Parameter variation with rationale:
  - Concurrency sweep (e.g., 1/2/4/8/16)
  - Prompt size sweep (small/medium/large) for LLM
  - Connections sweep for DB (1/4/8/16)
  - Explain why each parameter is varied (one paragraph per sweep)
- Scalability testing:
  - at least one sweep that demonstrates scaling behavior

Acceptance criteria:
- A “Design Rationale” section exists in each `reports/<id>/report.md` OR a shared `docs/methodology.md`.
- At least one plot in `reports/<id>/plots/` demonstrates scaling (e.g., throughput vs concurrency or p99 vs concurrency).

### 4) Preliminary result analysis
**Goal:** show you can interpret results beyond raw numbers.

Evidence to provide (must):
- Basic comparisons across configurations:
  - CLI `--compare <id1> <id2>` outputs a comparison table
  - (Optional) GUI comparison page
- Identification of bottlenecks:
  - compute vs memory vs storage vs network (at least hypotheses grounded in metrics)
- Resource usage profiling:
  - correlate throughput/latency with GPU utilization and memory usage

Acceptance criteria:
- Final report (or `docs/analysis.md`) includes:
  - at least 2 comparison findings (e.g., “p99 increases sharply after concurrency 8”)
  - at least 1 bottleneck conclusion supported by observed metrics

### 5) Reproducibility
**Goal:** a third party can rerun the same experiments with the same inputs.

Evidence to provide (must):
- Scripts/configs allow rerunning with same inputs:
  - recipe files are preserved
  - benchmark ID links to exact configuration used
- Environment details captured:
  - container image identifiers
  - software versions / modules used (as available)
  - git commit hash of the framework
- Documentation:
  - `docs/operations.md` describing how to run on MeluXina
  - `docs/methodology.md` describing metrics and how they are computed

Acceptance criteria:
- `results/<id>/run.json` exists and includes:
  - recipe hash + embedded recipe (or exact recipe path + copy)
  - git commit (if available)
  - service/client job IDs and hostnames
- A clean rerun procedure exists in docs (step-by-step) and is validated at least once.

---

## Guiding Rule for Implementation (MUST FOLLOW)
**Preserve what already works.**  
If a component is already implemented and working (e.g., CLI flow, manager orchestration, storage, Flask UI scaffolding), **keep it as-is** and only:
- extend it with backward-compatible features, or
- refactor it when strictly necessary to implement required capabilities, or
- fix correctness/reliability issues that block the plan.

Avoid “rewrite for cleanliness.” Prefer incremental, minimal changes that keep existing functionality working end-to-end.

## 0) Purpose of this document
This plan is written to be executed by an AI coding agent (e.g., Claude) to complete the project from **now (2026-01-07)** until **final delivery (end of March 2026)**.

It aligns the implementation with the **challenge architecture**:
- **Interface** (CLI + Web UI + APIs) to control the framework
- **Servers** module to start/stop/list/check services
- **Clients** module to start/stop/list/check clients (load generation)
- **Monitors** module to collect metrics as described in recipe, store metrics, show metrics, construct report
- **Logs** module to collect/view/save logs

**Important:** Before modifying any module, the agent must:
1. Identify whether the feature already exists in the repo (even partially).
2. If it exists and works, **reuse it** and add only the missing pieces.
3. If it exists but is incomplete, **extend** it (do not replace it wholesale).
4. If it does not exist, implement it with the smallest possible surface area.

It defines:
- The **user experience** required (CLI + GUI + artifacts + reports).
- A **minimal benchmark suite** that is actually useful for HPC engineers.
- A **phased roadmap** with week-by-week tasks and acceptance criteria.
- Concrete **file-level changes** and data contracts.
- Guardrails: what NOT to build, to keep scope realistic.

**Implementation note (preserve-first):**
The CLI section in this plan must remain aligned with the *current* flags implemented in `src/frontend.py`. When adding features (reports, compare, rerun), prefer adding new flags only if there is no existing equivalent behavior.

---

## 0.2 Agent Workflow for This Plan

For every task in this plan, the AI agent must follow this cycle:

1. **Implement**
   - Write or modify code to satisfy the task.
   - Prefer minimal, incremental changes that keep existing functionality working.
   - Add comments only when the logic is non-obvious.

2. **Verify**
   - Run the smallest possible smoke test to ensure the change doesn’t break existing behavior.
   - Example: `python src/frontend.py --list` should still list benchmarks after adding a new CLI flag.
   - If the change adds a new flag, run that flag once to ensure it parses without error.

3. **Test**
   - Run a minimal end-to-end test where feasible.
   - Example: If you add `--report <id>`, run a small benchmark and then `--report` to confirm it produces the file.
   - If full end-to-end isn’t possible, run the component in isolation (e.g., import the module and call the new function).

4. **Commit**
   - Commit with a concise, conventional commit message:
     - `feat: add --report flag to generate reports from artifacts`
     - `fix: correct prometheus metrics endpoint path`
     - `refactor: extract reporter logic from monitor.py`
   - Include the benchmark ID in the commit message if the change is tied to a specific run (optional).

**Important:** Do not batch multiple unrelated features in a single commit. One logical change per commit.

---

## 0.1 Challenge Slides Capability Checklist → Concrete Requirements (MUST IMPLEMENT)

This section maps the challenge slides (Servers/Clients/Monitors/Logs/Interface) to **concrete CLI + GUI requirements** and notes how to implement them while preserving the existing codebase.

### A) Servers module (start/stop/list/check services)
**Slide capabilities**
- Start and stop one (or several) service(s) on HPC
- List available services (recipes)
- List running services
- Check service

**Concrete requirements**
- CLI:
  - `python src/frontend.py <recipe.yaml>` must start service(s) and store service job metadata.
  - `python src/frontend.py --stop <benchmark_id>` stops service job(s) for that benchmark.
  - `python src/frontend.py --status <benchmark_id>` (or `--summary`) shows service job state and node.
  - `python src/frontend.py --list-recipes` (or reuse existing list command) lists available recipe files.
- GUI:
  - Benchmark detail page shows: service name/type, job id, node/hostname, state.
  - A “Stop” action (optional) or explicit CLI instructions for stopping.

**Implementation notes (preserve-first)**
- Preserve: `src/manager.py` (deploy_service), `src/service.py`, `src/storage.py`.
- Extend: add missing “stop/list/check” endpoints by reusing communicator’s Slurm commands.
- Health check: reuse/extend `src/health.py` (HTTP check + port check).

---

### B) Clients module (start/stop/list/check clients)
**Slide capabilities**
- Start and stop clients on HPC
- Clients can be single or multi-node (MVP: multi-client jobs; multi-node is stretch)
- List available clients (recipes)
- List running clients
- Check client status

**Concrete requirements**
- CLI:
  - `--watch <benchmark_id>` polls Slurm state for service and client jobs.
  - `--stop <benchmark_id>` cancels all client jobs for that benchmark (and service if required).
- GUI:
  - Benchmark detail page lists client jobs with state, job id, node.

**Implementation notes (preserve-first)**
- Preserve: `src/manager.py` (deploy_client/deploy_multiple_clients), `src/client.py`.
- Extend: implement stop/list/status using stored job IDs from storage.

---

### C) Monitors module (collect metrics in file, show metrics, construct report)
**Slide capabilities**
- Start/stop monitor instance (MVP: “collection step” can be on-demand; persistent monitor job is stretch)
- Collect metrics in a file
- Show metrics
- Construct report

**Concrete requirements**
- CLI:
  - `python src/frontend.py --metrics <benchmark_id>` collects:
    - Slurm job metrics (sacct)
    - GPU snapshot metrics (nvidia-smi) when applicable
    - request-level metrics aggregated from client output (JSONL)
    and writes to:
    - `results/<id>/summary.json`
    - `reports/<id>/plots/*.png` (at least one)
  - `python src/frontend.py --report <benchmark_id>` generates:
    - `reports/<id>/report.md`
    - `reports/<id>/report.json`
- GUI:
  - `/benchmark/<id>/metrics` shows summary table + embedded plot(s)
  - `/benchmark/<id>/report` shows report + download links

**Implementation notes (preserve-first)**
- Preserve: `src/monitor.py` (sacct + nvidia-smi collectors).
- Extend: add parsing/aggregation of request JSONL into `summary.json`.
- Plotting: prefer offline-safe PNG generation (no external CDNs).
- Reporting: add `src/reporter.py` only if it does not fit cleanly into `monitor.py`.

**Minimum generic monitor metrics (slide list)**
- Health check result (boolean + timestamp)
- CPU usage / memory usage (from sacct; optionally node-level if available)
- Disk I/O (optional; sacct may not expose)
- GPU usage + memory (nvidia-smi snapshot)
- Requests per second (from JSONL aggregation)

**LLM-specific (slide list)**
- Uptime seconds / model list (stretch unless service exposes endpoint)
- Process memory usage (stretch; can be approximated by GPU mem + sacct RSS)

---

### D) Logs module (get/show/save logs)
**Slide capabilities**
- Collect logs as described in recipe
- Start/stop log instance (MVP: on-demand download/save)
- Get logs
- Show logs
- Save logs

**Concrete requirements**
- CLI:
  - `--logs <benchmark_id>` displays available logs and/or tails.
  - `--download-logs <benchmark_id>` saves logs under `logs/<id>/` (or documented directory).
- GUI:
  - `/benchmark/<id>/logs` lists logs, allows viewing and basic search.

**Implementation notes (preserve-first)**
- Preserve: `src/logs.py` (download/search/aggregate).
- Extend: wire logs to GUI pages and ensure local caching is robust.

---

### E) Interface module (read/validate recipe, start/stop session, show status/logs/metrics, save report)
**Slide capabilities**
- Read and validate the recipe
- Start and stop a benchmark session
- List available bench recipes
- Show servers status
- Show client status
- Show logs
- Show metrics
- Save report
- Interface can be CLI + GUI + APIs

**Concrete requirements**
- CLI:
  - Recipe validation errors are actionable (line/field-level if possible).
  - Session stop cancels all jobs belonging to the benchmark id.
- GUI:
  - A top-level navigation for Dashboard / Benchmarks / CLI Reference already exists; extend with Metrics/Logs/Report links.
  - Provide artifact downloads: `run.json`, `requests.jsonl`, `summary.json`, `report.md`, plots.

**Implementation notes (preserve-first)**
- Preserve: `src/frontend.py` structure and existing `src/web/flask_app.py`.
- Extend: add missing CLI flags only if not already present; otherwise reuse/rename minimally.

---

### Acceptance criteria for checklist (Definition of Done for challenge parity)
- From CLI: user can run, stop, list, watch, view logs, collect metrics, generate report.
- From GUI: user can browse benchmarks and view status + logs + metrics + report; can download report and summary artifacts.
- Artifacts exist for each benchmark under `results/<id>/` and `reports/<id>/`.

---

## 1) Project Vision & Differentiation
Other teams often focus on heavy “monitoring stack” features (Prometheus/Grafana) and LLM-generated “enterprise architecture.”  
**We will match the required experience** (CLI + GUI + reports + metrics viewing) required by the challenge, but differentiate by delivering:

### 1.1 Engineer-grade benchmark suite
Benchmarks should help an engineer answer:
- Where does the cluster saturate (throughput vs concurrency)?
- What is the tail latency (P95/P99) under load?
- What is resource efficiency (tokens/sec/GPU, TPS/CPU)?
- Are results reproducible (recipe + code + container hash + node/partition)?

### 1.2 Reproducibility-first
Each run must produce a standardized artifact bundle:
- raw per-request data (JSONL)
- aggregated summary (JSON)
- human-readable report (Markdown)
- plots (PNG) for GUI + slides

---

## 2) Non-Negotiable User Experience (Parity Requirement)
This section maps directly to the “Interface” module in the challenge architecture: **API/GUI/CLI** for controlling the framework and viewing outputs (status, logs, metrics, reports).

### 2.1 CLI (must)
Users must be able to:
- Run a benchmark from a recipe
- List benchmarks
- Inspect a benchmark
- Watch status (polling)
- View/download logs
- Collect metrics
- Generate and view reports
- Compare two benchmark runs (at least a simple table)

Recommended CLI commands (aligned with current `src/frontend.py` flags):

### Already implemented (keep as-is)
- Run a benchmark:
  - `python src/frontend.py <recipe.yaml>`
- Interactive CLI:
  - `python src/frontend.py --ui`
- List benchmarks:
  - `python src/frontend.py --list`
  - `python src/frontend.py --list-benchmarks` (alias)
- Show benchmark summary:
  - `python src/frontend.py --summary <BENCHMARK_ID>`
- Watch live status:
  - `python src/frontend.py --watch <BENCHMARK_ID>`
- Show logs:
  - `python src/frontend.py --logs <BENCHMARK_ID>`
- Collect & show metrics:
  - `python src/frontend.py --metrics <BENCHMARK_ID>`
- Stop a benchmark session (cancel jobs):
  - `python src/frontend.py --stop <BENCHMARK_ID>`
- Load existing benchmark context (non-interactive “open” by id):
  - `python src/frontend.py --id <BENCHMARK_ID>`
- Launch web UI (Flask):
  - `python src/frontend.py --web` (launches `src/web/flask_app.py`)
  - `python src/web/flask_app.py` (direct launch)

### Missing (must be added; implement in a preserve-first way)
- Generate report artifacts (Markdown/JSON/plots):
  - `python src/frontend.py --report <BENCHMARK_ID>`
- Compare two benchmark runs and flag regressions (KF4):
  - `python src/frontend.py --compare <BENCHMARK_ID_1> <BENCHMARK_ID_2>`
- (Optional) Rerun an existing benchmark using the stored metadata bundle (KF3):
  - `python src/frontend.py --rerun <BENCHMARK_ID>`
- (Optional) Download/cache logs locally (if not already exposed via UI flow):
  - `python src/frontend.py --download-logs <BENCHMARK_ID>`
- (Optional) List available recipe files (if not already provided via the interactive UI):
  - `python src/frontend.py --list-recipes` (or document “recipes live under `examples/` and `examples/**/`”)

Preservation note:
- Do not rename or remove existing flags. Add missing flags only if the capability does not already exist under a different name.
- If any of these flags already exist (even with slightly different names/behavior), **keep the existing CLI UX** and extend it rather than introducing parallel flags.
- Only add new flags when a capability is truly missing.

### 2.2 Web GUI (must)
Users must be able to:
- See dashboard: recent benchmarks + counts
- Browse benchmark list
- Open benchmark detail
- View servers status and client status for a benchmark (job state, node, timings)
- View collected metrics (summary + plots)
- View report (render markdown or show raw)
- Browse logs (at minimum show downloaded logs; ideally remote+local)
- Download artifacts (report/summary/raw JSONL)

Start command (Flask):
- Preferred: `python src/frontend.py --web`
- Also supported: `python src/web/flask_app.py`

Preservation note:
- The existing Flask UI is a strong base; **do not rewrite** it into another framework.
- Extend it by adding routes/pages that read the new artifacts (`results/`, `reports/`) while keeping existing dashboard/list pages intact.

### 2.3 Reports (must)
Reports must be viewable:
- as files under `reports/<benchmark_id>/report.md` (and `report.json`)
- via GUI (a “Report” page)

---

## 3) Scope & Guardrails (to keep delivery feasible)

### 3.Y Monitoring Files to Create (Prepare for Easy Integration)

These files should be created during Month 2 to enable trivial Prometheus/Grafana activation later:

**Directory structure to create:**
```
Team1_EUMASTER4HPC2526/
├── containers/                    # Apptainer container definitions
│   ├── prometheus.def
│   ├── grafana.def
│   └── pushgateway.def
├── config/
│   ├── prometheus.yml             # Prometheus scrape config template
│   └── grafana/
│       ├── provisioning/
│       │   ├── dashboards/
│       │   │   └── default.yaml   # Dashboard provisioning config
│       │   └── datasources/
│       │       └── prometheus.yaml
│       └── dashboards/
│           ├── llm-inference.json
│           └── database-benchmark.json
```

**Implementation task (add to Week 2 or 3):**
- [ ] Create `containers/` directory with `.gitkeep`
- [ ] Create `config/` directory structure with `.gitkeep` files
- [ ] Create placeholder container .def files (can be minimal initially)
- [ ] Create `config/prometheus.yml` template
- [ ] Create basic Grafana dashboard JSON files

### 3.X Optional Monitoring Stack (Prometheus/Grafana) — Add-on Track

We will keep the core system **artifact-first** and **offline-safe**, but offer an **optional** Prometheus/Grafana integration that can be launched when the core is complete.

**Policy**
- Default mode: **local artifacts** (summary JSON + plots + GUI)
- Optional mode: **prometheus_grafana** (only if enabled in recipe/CLI)

**Requirements**
- Must not block core functionality.
- Must not replace the existing monitor/report pipeline; it only augments it.
- Must be runnable on MeluXina with minimal assumptions (ports/tunneling documented).

---

### 3.X.1 Prometheus/Grafana Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MeluXina HPC Cluster                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │  Service Node   │  │  Client Node(s) │  │  Monitor Node   │          │
│  │  (GPU)          │  │  (CPU)          │  │  (CPU)          │          │
│  │                 │  │                 │  │                 │          │
│  │  vLLM/Ollama    │  │  Benchmark      │  │  Prometheus     │          │
│  │  :8000/:11434   │  │  Clients        │  │  :9090          │          │
│  │                 │  │                 │  │                 │          │
│  │  Metrics        │  │  Pushgateway    │  │  Grafana        │          │
│  │  Exporter       │◄─┤  :9091          │◄─┤  :3000          │          │
│  │  :9100          │  │                 │  │                 │          │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘          │
│           │                    │                    │                    │
└───────────┼────────────────────┼────────────────────┼────────────────────┘
            │                    │                    │
            └────────────────────┴────────────────────┘
                                 │ SSH Tunnel
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Laptop                                    │
│                                                                          │
│   Browser → localhost:3000 (Grafana) ──────────────────────────────────►│
│   Browser → localhost:9090 (Prometheus) ───────────────────────────────►│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 3.X.2 Preparation: Metrics Endpoint in Benchmark Clients (Month 2 Week 4)

To make Prometheus integration trivial later, **prepare metrics endpoints now** even if not used initially.

**Step 1: Add Prometheus-format metrics output to client scripts**

Every client script should optionally emit Prometheus-compatible metrics. Add this to `src/command_builders.py` client templates:

```bash
# At the end of each benchmark client script, emit Prometheus metrics
cat << EOF > /tmp/benchmark_metrics.prom
# HELP benchmark_requests_total Total benchmark requests
# TYPE benchmark_requests_total counter
benchmark_requests_total{service="$SERVICE_TYPE",benchmark_id="$BENCHMARK_ID"} $TOTAL_REQUESTS

# HELP benchmark_requests_success Successful requests
# TYPE benchmark_requests_success counter
benchmark_requests_success{service="$SERVICE_TYPE",benchmark_id="$BENCHMARK_ID"} $SUCCESS_COUNT

# HELP benchmark_latency_seconds Request latency
# TYPE benchmark_latency_seconds summary
benchmark_latency_seconds{service="$SERVICE_TYPE",quantile="0.5"} $P50_LATENCY
benchmark_latency_seconds{service="$SERVICE_TYPE",quantile="0.9"} $P90_LATENCY
benchmark_latency_seconds{service="$SERVICE_TYPE",quantile="0.99"} $P99_LATENCY

# HELP benchmark_throughput_rps Requests per second
# TYPE benchmark_throughput_rps gauge
benchmark_throughput_rps{service="$SERVICE_TYPE",benchmark_id="$BENCHMARK_ID"} $RPS
EOF
```

**Step 2: Add `/metrics` endpoint helper to monitor module**

Add to `src/monitor.py`:

```python
def format_prometheus_metrics(summary: dict, benchmark_id: str, service_type: str) -> str:
    """Format summary.json data as Prometheus exposition format."""
    lines = [
        "# HELP benchmark_requests_total Total benchmark requests",
        "# TYPE benchmark_requests_total counter",
        f'benchmark_requests_total{{benchmark_id="{benchmark_id}",service="{service_type}"}} {summary.get("total_requests", 0)}',
        "",
        "# HELP benchmark_success_rate Success rate percentage", 
        "# TYPE benchmark_success_rate gauge",
        f'benchmark_success_rate{{benchmark_id="{benchmark_id}",service="{service_type}"}} {summary.get("success_rate", 0)}',
        "",
        "# HELP benchmark_latency_seconds Request latency in seconds",
        "# TYPE benchmark_latency_seconds summary",
        f'benchmark_latency_seconds{{benchmark_id="{benchmark_id}",quantile="0.5"}} {summary.get("latency_s", {}).get("p50", 0)}',
        f'benchmark_latency_seconds{{benchmark_id="{benchmark_id}",quantile="0.9"}} {summary.get("latency_s", {}).get("p90", 0)}',
        f'benchmark_latency_seconds{{benchmark_id="{benchmark_id}",quantile="0.99"}} {summary.get("latency_s", {}).get("p99", 0)}',
        "",
        "# HELP benchmark_throughput_rps Throughput in requests per second",
        "# TYPE benchmark_throughput_rps gauge",
        f'benchmark_throughput_rps{{benchmark_id="{benchmark_id}",service="{service_type}"}} {summary.get("requests_per_second", 0)}',
    ]
    return "\n".join(lines)
```

**Step 3: Add `/api/metrics/prometheus` endpoint to Flask GUI**

Add to `src/web/flask_app.py`:

```python
@app.route('/api/benchmark/<benchmark_id>/metrics/prometheus')
def prometheus_metrics(benchmark_id):
    """Export benchmark metrics in Prometheus format."""
    summary_path = Path(f"results/{benchmark_id}/summary.json")
    if not summary_path.exists():
        return "# No metrics available\n", 404, {'Content-Type': 'text/plain'}
    
    with open(summary_path) as f:
        summary = json.load(f)
    
    from monitor import format_prometheus_metrics
    metrics_text = format_prometheus_metrics(summary, benchmark_id, summary.get("service_type", "unknown"))
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}
```

---

### 3.X.3 Prometheus/Grafana Service Containers (Month 2 Week 4)

Create container definition files for easy deployment:

**File: `containers/prometheus.def`** (Apptainer definition)
```
Bootstrap: docker
From: prom/prometheus:latest

%files
    prometheus.yml /etc/prometheus/prometheus.yml

%runscript
    exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --web.listen-address=0.0.0.0:9090
```

**File: `containers/grafana.def`**
```
Bootstrap: docker
From: grafana/grafana:latest

%runscript
    exec /run.sh
```

**File: `containers/pushgateway.def`**
```
Bootstrap: docker
From: prom/pushgateway:latest

%runscript
    exec /bin/pushgateway --web.listen-address=0.0.0.0:9091
```

**File: `config/prometheus.yml`** (template)
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'benchmark-metrics'
    static_configs:
      - targets: ['localhost:5000']  # Flask GUI metrics endpoint
    metrics_path: '/api/benchmark/<benchmark_id>/metrics/prometheus'
    
  - job_name: 'pushgateway'
    static_configs:
      - targets: ['localhost:9091']
    honor_labels: true
```

---

### 3.X.4 Recipe Configuration for Monitoring

**Extended recipe schema:**

```yaml
configuration:
  target: "meluxina"

# ... service and client sections ...

monitoring:
  enabled: false  # Set to true to enable Prometheus/Grafana
  mode: "local"   # "local" (default) or "prometheus_grafana"
  
  prometheus:
    partition: "cpu"
    time_limit: "04:00:00"
    port: 9090
    scrape_interval: "15s"
    
  grafana:
    partition: "cpu" 
    time_limit: "04:00:00"
    port: 3000
    admin_password: "benchmark"  # Default password
    
  pushgateway:
    enabled: true
    port: 9091
    
  # Pre-built dashboard to load
  dashboards:
    - "llm-inference"      # LLM metrics dashboard
    - "database-benchmark" # DB metrics dashboard
```

---

### 3.X.5 One-Command Monitoring Activation

**CLI command to enable monitoring:**

```bash
# Enable monitoring for a new benchmark
python src/frontend.py examples/recipe_vllm.yaml --with-monitoring

# Enable monitoring for existing/running benchmark
python src/frontend.py --enable-monitoring <benchmark_id>

# Get monitoring access info
python src/frontend.py --monitoring-info <benchmark_id>
```

**Output of `--monitoring-info`:**
```
Monitoring Stack for Benchmark #42
==================================

Prometheus: Running on mel0142:9090
Grafana:    Running on mel0142:3000

To access from your laptop:

1. Open SSH tunnel:
   ssh -L 3000:mel0142:3000 -L 9090:mel0142:9090 meluxina

2. Open in browser:
   Grafana:    http://localhost:3000 (admin/benchmark)
   Prometheus: http://localhost:9090

Pre-loaded dashboards:
  - LLM Inference Metrics
  - System Resources
```

---

### 3.X.6 Pre-Built Grafana Dashboards (Month 2 Week 4)

Create dashboard JSON files that auto-load when Grafana starts:

**File: `config/grafana/dashboards/llm-inference.json`**

Key panels to include:
- Requests per second (time series)
- Latency percentiles (P50/P90/P99) (time series)
- Success rate (gauge)
- Tokens per second (for LLM) (time series)
- GPU utilization (if available)
- Error count (counter)

**File: `config/grafana/dashboards/database-benchmark.json`**

Key panels to include:
- Transactions per second (time series)
- Query latency percentiles (time series)
- Insert vs Select breakdown (pie chart)
- Connection count (gauge)
- Error rate (time series)

**File: `config/grafana/provisioning/dashboards/default.yaml`**
```yaml
apiVersion: 1
providers:
  - name: 'Benchmark Dashboards'
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

---

### 3.X.7 Implementation Checklist for Monitoring Integration

**Phase 1: Preparation (Do during Month 2)**
- [ ] Add `format_prometheus_metrics()` to `src/monitor.py`
- [ ] Add `/api/benchmark/<id>/metrics/prometheus` endpoint to Flask
- [ ] Create `containers/` directory with .def files
- [ ] Create `config/prometheus.yml` template
- [ ] Create basic Grafana dashboard JSON files
- [ ] Update recipe schema to support `monitoring:` section

**Phase 2: Integration (Do after MVP is stable, Month 3-4)**
- [ ] Implement `--with-monitoring` flag in frontend.py
- [ ] Implement `--enable-monitoring <id>` command
- [ ] Implement `--monitoring-info <id>` command
- [ ] Add monitoring service deployment to Manager
- [ ] Add monitoring status to `--summary` output
- [ ] Add "Monitoring" section to Web GUI benchmark detail page
- [ ] Build Apptainer containers on MeluXina: `apptainer build prometheus.sif containers/prometheus.def`

**Phase 3: Polish (Stretch, if time permits)**
- [ ] Auto-configure Prometheus scrape targets based on running jobs
- [ ] Add alerting rules for common issues (high error rate, latency spike)
- [ ] Create more specialized dashboards per service type
- [ ] Add Grafana annotations for benchmark start/end events

### 3.X.8 Quick Start Guide for Monitoring (Include in docs/operations.md)

```markdown
## Enabling Real-Time Monitoring (Optional)

By default, the framework uses artifact-based metrics (no live monitoring needed).
If you want real-time Grafana dashboards:

### Option 1: Enable for a new benchmark
python src/frontend.py examples/recipe_vllm.yaml --with-monitoring

### Option 2: Enable for a running benchmark  
python src/frontend.py --enable-monitoring <benchmark_id>

### Access the dashboards
python src/frontend.py --monitoring-info <benchmark_id>
# Follow the SSH tunnel instructions printed

### Disable monitoring (stop the monitoring jobs)
python src/frontend.py --stop-monitoring <benchmark_id>
```

---

### 3.X.8 Why This Approach is Better Than Other Teams

| Aspect | Other Teams | Our Approach |
|--------|-------------|--------------|
| **Default mode** | Prometheus required | Artifact-first (works offline) |
| **Integration effort** | Heavy (always running) | Opt-in (one flag to enable) |
| **Data persistence** | Only in Prometheus | JSON artifacts + optional Prometheus |
| **Offline analysis** | Not possible | Full capability via artifacts |
| **Setup complexity** | SSH tunnels required | Tunnels only when monitoring enabled |
| **Dashboard creation** | Manual | Pre-built dashboards auto-loaded |

**Key differentiator**: Our users get full functionality without Prometheus, but can enable it with one flag when they want real-time visualization. Other teams require Prometheus/Grafana setup to see any metrics.

**Acceptance criteria**
- When enabled, the GUI shows a "Monitoring" section with:
  - Grafana URL (or tunnel command)
  - Prometheus health status
- When disabled, nothing breaks and all local artifacts still work.

## 3.0 Current Codebase: Preserve vs Extend (EXPLICIT)
The agent must treat these as constraints.

### Preserve (already implemented and should remain the backbone)
- `src/frontend.py`: recipe parsing + CLI entry point (do not rewrite; extend flags/commands only as needed)
- `src/manager.py`: service/client orchestration via Slurm (extend lifecycle features; do not redesign core flow)
- `src/communicator.py`: SSH + Slurm command execution (keep)
- `src/service.py`, `src/client.py`: data models (keep; extend metadata if needed)
- `src/storage.py`: persistence and listing/summaries (keep; extend for artifacts index if needed)
- `src/command_builders.py`: generates service/client commands (keep; extend client scripts to emit JSONL)
- `src/web/flask_app.py`: Flask GUI (keep; extend routes for metrics/logs/reports pages)
- `src/health.py`: basic health checks exist (extend only if needed)
- `src/monitor.py`: basic Slurm + GPU metrics collection exists (extend with aggregation for requests JSONL; keep existing sacct/nvidia-smi logic)
- `src/logs.py`: basic log download/search exists (extend for GUI integration and artifact wiring)

### Extend (capabilities incomplete, must be completed)
- Service lifecycle controls: stop/list/check service(s)
- Client lifecycle controls: stop/list/check clients
- Monitor: “collect metrics in a file” + “show metrics” + “construct report”
- Logs: list/get/show/save logs (local caching + GUI pages)
- Reporting: standardized report + plots + comparison (new module may be added, but do not replace existing monitor/logs)

### Add (minimal new modules/files only if required)
- `src/reporter.py` for report generation and plots (separation of concerns: monitor collects, reporter presents)
- `docs/` methodology and dataset index docs

### 3.1 MVP Services (required)
These are required for challenge coverage and must be fully integrated end-to-end (recipe → deploy → health → clients → metrics → report → GUI):
- **Inference**: vLLM, Ollama
- **Storage**: PostgreSQL
- **Retrieval**: ChromaDB

### 3.2 “High-Value Additions” (strongly recommended)
These additions increase practical utility for AI factory users and improve challenge coverage (storage + retrieval + inference engines):
- **Redis** (in-memory database / cache): fast, common, easy to benchmark and interpret
- **MinIO** (S3-compatible object storage): extremely relevant for AI pipelines (datasets, artifacts)
- **Qdrant** (vector database): widely used; complements Chroma and enables meaningful retrieval comparisons
- **Triton Inference Server** (optional): aligns with challenge “inference engines: Triton”; can be added as an opt-in service

### 3.3 Stretch (optional if time permits)
- Parameter sweeps framework (multi-run automation)
- Rich comparisons across many runs (trend dashboards)
- Live log streaming from remote
- Optional Prometheus/Grafana add-on (already planned)
- Advanced LLM metrics (TTFT/TPOT with streaming, if feasible in vLLM/Ollama mode)

### 3.4 Low-Friction Implementation Order (MANDATORY FOR THE AGENT)
This section defines the exact order the agent must follow to minimize friction and avoid building “new services” on top of an unstable measurement pipeline.

**Note on Reporter:** Use `src/reporter.py` for all report/plot generation logic to keep `src/monitor.py` focused purely on data collection.

#### Stage 0 — Stabilize the baseline pipeline (M0 + Week 1 focus)
Goal: make the existing services (vLLM/Ollama/Postgres/Chroma) produce consistent artifacts and metrics.

Order:
1. Standardize artifacts for *existing* clients:
   - Ensure clients emit `requests.jsonl` lines (or can be parsed from logs) with the agreed schema.
2. Implement local aggregation:
   - `results/<id>/summary.json` created from JSONL + job metrics.
3. Implement report + plots:
   - `reports/<id>/report.md`, `reports/<id>/plots/*.png`
4. Wire GUI pages:
   - Benchmark detail shows status + links; Metrics/Logs/Report pages render artifacts.

Acceptance:
- One-command run with an existing recipe yields: `run.json`, `requests.jsonl`, `summary.json`, `report.md`, plots, and GUI can display them.

#### Stage 1 — Add Redis (lowest friction, high value)
Why first:
- Minimal dependencies, small container, stable performance.
- Great for concurrency sweeps and saturation finder (KF1).

Work:
- Add `redis` service builder (container image + port + command).
- Add `redis_benchmark` client builder (prefer `redis-benchmark` if present; fallback to `redis-cli` loop).
- Metrics (meaningful):
  - ops/sec, p50/p95/p99 latency, error rate, bytes/sec (derived).
- Add recipes:
  - `examples/recipe_redis.yaml` (smoke) and `examples/recipe_redis_stress.yaml` (sweep-ready).
- Ensure JSONL output is produced.

Acceptance:
- Redis run produces full artifacts and shows in GUI; KF1 works on a concurrency sweep.

#### Stage 2 — Add MinIO (moderate friction, very high AI-factory value)
Why second:
- Object storage is core to AI factories and is easy to interpret (PUT/GET bandwidth, tail latency).
- Requires a client tool; keep it simple.

Work:
- Add `minio` service builder (image + ports + env vars + start command).
- Add `minio_client` benchmark client:
  - Prefer `mc` (MinIO client) if available; fallback to signed S3 requests is too complex—avoid.
  - Workload: PUT/GET fixed-size objects; concurrency sweep via multiple clients.
- Metrics:
  - put/get ops/sec, bytes/sec, p50/p95/p99 latency, success rate.
- Add recipes:
  - `examples/recipe_minio.yaml`, `examples/recipe_minio_stress.yaml`.

Acceptance:
- MinIO run yields full artifacts and clearly shows bandwidth vs concurrency.

#### Stage 3 — Add Qdrant (moderate friction, high retrieval realism)
Why third:
- Retrieval comparison is a strong evaluation point; Qdrant has clean HTTP APIs.
- Complements existing Chroma.

Work:
- Add `qdrant` service builder (image + ports).
- Add `qdrant_stress` client builder (HTTP curl):
  - Create collection, insert points (batched), query points.
- Metrics:
  - insert vps, query qps, p50/p95/p99 query latency, success rate.
  - (Optional) recall@k only if you can define ground truth in recipe/dataset.
- Add recipes:
  - `examples/recipe_qdrant.yaml`, `examples/recipe_qdrant_stress.yaml`.

Acceptance:
- Qdrant run yields full artifacts; a report compares Chroma vs Qdrant on the same dataset size/dim.

#### Stage 4 — Add Triton (highest friction; keep minimal, opt-in)
Why last:
- Triton requires model repository packaging; it is easy to burn time here.
- Only needed to satisfy “Triton inference engines” checkbox and offer an advanced option.

Work (minimal credible implementation):
- Add `triton` service builder (container image + ports + model repo bind).
- Provide exactly one “known-good” model repo example in `examples/` (or documented download step).
- Client:
  - Use HTTP endpoint with a simple request; focus on latency/RPS.
- Metrics:
  - p50/p95/p99, RPS, success rate; link to Triton `/metrics`.
- Add recipe:
  - `examples/recipe_triton.yaml` (clearly documented prerequisites).

Acceptance:
- Triton recipe can be run with documented prerequisites; artifacts produced; optional Grafana can scrape `/metrics`.

#### Stage 5 — Optional Prometheus/Grafana integration (only after Stage 0–3 are done)
- Do not start this until artifacts, reports, GUI are stable.
- Keep opt-in and never block core operation.

---

## 3.5 Service-Specific Configuration & Metrics (MUST BE COMPLETE)

Each supported service must have:
1. Full recipe configuration options documented (service + client)
2. Meaningful metrics collected and displayed (service-specific + generic)
3. Health check endpoint defined
4. Default values that work out-of-the-box
5. Benchmark outputs in standardized artifacts (`run.json`, `requests.jsonl`, `summary.json`, `report.md`, plots)
6. GUI shows: status + logs + metrics + report downloads

### Service: vLLM (LLM Inference)

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `facebook/opt-125m` | HuggingFace model ID |
| `tensor_parallel_size` | int | 1 | GPUs for tensor parallelism |
| `max_model_len` | int | null | Max context length |
| `gpu_memory_utilization` | float | 0.9 | GPU memory fraction |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | (from service) | Model to query |
| `num_requests` | int | 50 | Total requests |
| `max_tokens` | int | 64 | Max output tokens |
| `prompt` | string | "Hello world" | Test prompt |
| `warmup_delay` | int | 30 | Seconds to wait for model load |
| `concurrent_requests` | int | 1 | Parallel requests (for sweeps) |

**Metrics to Collect** (in `summary.json`):
| Metric | Unit | Description |
|--------|------|-------------|
| `latency_avg` | seconds | Mean request latency |
| `latency_p50/p90/p95/p99` | seconds | Latency percentiles |
| `requests_per_second` | RPS | Throughput |
| `tokens_per_second` | TPS | Output token throughput |
| `ttft_avg/p99` | seconds | Time to first token (if streaming) |
| `success_rate` | % | Successful requests |
| `error_count` | count | Failed requests |

**Health Check**:
- Endpoint: `GET /health` or `GET /v1/models`
- Success: HTTP 200

---

### Service: Ollama (LLM Inference)

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `llama2` | Model name to pull |
| `warmup_seconds` | int | 5 | Wait for server startup |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | (from service) | Model to query |
| `num_requests` | int | 5 | Total requests |
| `max_retries` | int | 30 | Retries waiting for service |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `latency_avg` | seconds | Mean request latency |
| `latency_p50/p90/p95/p99` | seconds | Latency percentiles |
| `requests_per_second` | RPS | Throughput |
| `success_rate` | % | Successful requests |

**Health Check**:
- Endpoint: `GET /api/tags`
- Success: HTTP 200 with JSON response

---

### Service: PostgreSQL (Relational Database)

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `db_name` | string | `benchmark` | Database name |
| `data_dir` | string | `/tmp/pgdata` | Data directory |
| `auth` | string | `trust` | Authentication method |
| `tuning.shared_buffers` | string | `128MB` | Shared buffer size |
| `tuning.effective_cache_size` | string | `512MB` | Cache size hint |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `db_name` | string | `benchmark` | Database to connect |
| `num_inserts` | int | 10000 | Insert operations |
| `num_selects` | int | 5000 | Select operations |
| `table_name` | string | `stress_test` | Test table name |
| `warmup_delay` | int | 5 | Seconds before starting |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `insert_tps` | TPS | Insert transactions/second |
| `select_qps` | QPS | Select queries/second |
| `insert_duration` | seconds | Total insert phase time |
| `select_duration` | seconds | Total select phase time |
| `total_duration` | seconds | Complete test time |

**Health Check**:
- Method: `psql -h $HOST -p 5432 -U postgres -c "SELECT 1"`
- Success: Returns "1"

---

### Service: ChromaDB (Vector Database) — MVP (Retrieval)
ChromaDB is part of the retrieval category required by the challenge. We keep it curl-based to avoid Python dependency issues on compute nodes.

**Low-friction improvement to implement early**:
- Replace `python3 -c "import random; ..."` in the Chroma stress client with a pure-shell deterministic generator (or pre-generated embeddings) to avoid Python availability issues on compute nodes.
- If Python is guaranteed on MeluXina compute nodes, keep current approach but ensure JSONL timing is emitted per insert/query so latency percentiles can be computed.

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `host` | string | `0.0.0.0` | Bind address |
| `port` | int | 8000 | Service port |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `num_vectors` | int | 1000 | Vectors to insert |
| `dim` | int | 128 | Embedding dimension |
| `num_queries` | int | 100 | Query operations |
| `top_k` | int | 10 | Results per query |
| `warmup_delay` | int | 5 | Seconds before starting |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `insert_vps` | VPS | Vectors inserted/second |
| `query_qps` | QPS | Queries/second |
| `insert_duration` | seconds | Total insert time |
| `query_duration` | seconds | Total query time |
| `latency_p50/p95/p99` | seconds | Optional if per-query JSONL timing is emitted |

**Health Check**:
- Endpoint: `GET /api/v2/heartbeat`
- Success: HTTP 200

---

### Service: Redis (In-Memory Database / Cache) — HIGH-VALUE ADDITION (Storage)
Redis is extremely common in AI factories (caching embeddings, rate limits, queues). It is also ideal for scalability and saturation studies because it is fast and stable.

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `port` | int | 6379 | Redis port |
| `appendonly` | bool | false | Enable AOF persistence |
| `save` | string | "" | Snapshot config (empty disables RDB) |
| `maxmemory` | string | "" | Optional memory cap (e.g., `4gb`) |
| `maxmemory_policy` | string | "noeviction" | Eviction policy (if maxmemory set) |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `num_requests` | int | 10000 | Total operations |
| `key_size_bytes` | int | 32 | Key size |
| `value_size_bytes` | int | 256 | Value size |
| `pipeline` | int | 1 | Pipeline depth (optional) |
| `operation_mix` | string | "get:set=50:50" | Mix of operations |
| `warmup_delay` | int | 5 | Seconds before starting |
| `concurrent_clients` | int | 1 | For sweeps (1/2/4/8/16/…) |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `ops_per_second` | OPS | Operations per second |
| `latency_p50/p95/p99` | seconds | Tail latency under load |
| `success_rate` | % | Errors/timeouts |
| `bytes_per_second` | B/s | Approx throughput from payload sizes |

**Health Check**:
- Method: `redis-cli -h $SERVICE_HOSTNAME -p $SERVICE_PORT PING`
- Success: returns `PONG`

---

### Service: MinIO (S3 Object Storage) — HIGH-VALUE ADDITION (Storage)
MinIO is central to AI workflows (datasets, model artifacts). We benchmark object PUT/GET performance and tail latencies.

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `port` | int | 9000 | S3 API port |
| `console_port` | int | 9001 | Admin console port |
| `root_user` | string | "minioadmin" | Access key |
| `root_password` | string | "minioadmin" | Secret key |
| `data_dir` | string | "/data" | Data path inside container |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `object_size_bytes` | int | 1048576 | Object size (1MB default) |
| `num_objects` | int | 100 | Number of objects |
| `operation_mix` | string | "put:get=50:50" | Mix for workload |
| `bucket` | string | "benchmark" | Bucket name |
| `warmup_delay` | int | 10 | Seconds before starting |
| `concurrent_clients` | int | 1 | For sweeps |
| `use_https` | bool | false | If TLS enabled |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `put_ops_per_second` | OPS | PUT throughput |
| `get_ops_per_second` | OPS | GET throughput |
| `put_bytes_per_second` | B/s | Upload bandwidth |
| `get_bytes_per_second` | B/s | Download bandwidth |
| `latency_p50/p95/p99` | seconds | Tail latency |
| `success_rate` | % | Error rate |

**Health Check**:
- Endpoint: `GET /minio/health/ready`
- Success: HTTP 200

---

### Service: Qdrant (Vector Database) — HIGH-VALUE ADDITION (Retrieval)
Qdrant is widely used in production retrieval. It complements Chroma and allows comparative retrieval benchmarking.

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `port` | int | 6333 | HTTP API port |
| `grpc_port` | int | 6334 | gRPC port (optional) |
| `storage_path` | string | "/qdrant/storage" | Data directory |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `collection` | string | "benchmark" | Collection name |
| `dim` | int | 128 | Vector dimension |
| `num_points` | int | 10000 | Points to insert |
| `batch_size` | int | 256 | Insert batch size |
| `num_queries` | int | 1000 | Query ops |
| `top_k` | int | 10 | Results per query |
| `warmup_delay` | int | 10 | Seconds before starting |
| `concurrent_clients` | int | 1 | For sweeps |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `insert_vps` | VPS | Points inserted/second |
| `query_qps` | QPS | Queries/second |
| `latency_p50/p95/p99` | seconds | Tail query latency |
| `success_rate` | % | Errors/timeouts |
| `recall_at_k` | ratio | Optional (requires known ground truth) |

**Health Check**:
- Endpoint: `GET /healthz`
- Success: HTTP 200

---

### Service: Triton Inference Server — OPTIONAL ADDITION (Inference Engines)
Triton is explicitly listed in the challenge. We include it as an **opt-in** service (not default) because the model packaging can be complex. The goal is to satisfy the category with a minimal but credible benchmark.

**Recipe Configuration** (`service.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `http_port` | int | 8000 | HTTP port |
| `grpc_port` | int | 8001 | gRPC port |
| `metrics_port` | int | 8002 | Prometheus metrics port |
| `model_repo` | string | "/models" | Path to model repository |
| `log_verbose` | int | 0 | Triton verbosity |

**Client Configuration** (`client.settings`):
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `scenario` | string | "http" | http/grpc client path |
| `num_requests` | int | 1000 | Total requests |
| `concurrent_clients` | int | 1 | Concurrency sweep |
| `payload_size_bytes` | int | 0 | Optional payload sizing |
| `warmup_delay` | int | 10 | Seconds before starting |

**Metrics to Collect**:
| Metric | Unit | Description |
|--------|------|-------------|
| `requests_per_second` | RPS | Throughput |
| `latency_p50/p95/p99` | seconds | Latency percentiles |
| `success_rate` | % | Error rate |
| `server_metrics_url` | string | Link to Triton `/metrics` (Prometheus format) |

**Health Check**:
- Endpoint: `GET /v2/health/ready`
- Success: HTTP 200

---


### Adding New Services (Extension Guide)

To add a new service type:

1. **Add service command builder** in `src/command_builders.py`:
   ```python
   def build_myservice_service_command(settings: Dict[str, Any]) -> str:
       # Generate startup command
       return "myservice start ..."
   ```

2. **Add client command builder** in `src/command_builders.py`:
   ```python
   def build_myservice_stress_client_command(settings: Dict[str, Any]) -> str:
       # Generate benchmark script that emits JSONL
       return """
       for i in $(seq 1 $NUM_REQUESTS); do
           start=$(date +%s.%N)
           # ... run request ...
           end=$(date +%s.%N)
           echo '{"request_id":'$i',"latency_s":'$(echo "$end-$start"|bc)',"success":true}'
       done
       """
   ```

3. **Register in SERVICE_BUILDERS and CLIENT_BUILDERS** dictionaries

4. **Add default image and port** in `get_default_image()` and `get_default_port()`

5. **Document in this plan** with configuration table and metrics table

### 3.6 Explicitly out of scope (do NOT build)
- Full Prometheus/Grafana stack orchestration **as the default** (but prepare for easy opt-in)
- Distributed Ray clusters / multi-node model parallelism
- MLPerf compliance harness
- Kubernetes support

### 3.7 Project File Structure (Complete)

```
Team1_EUMASTER4HPC2526/
├── src/
│   ├── frontend.py              # CLI entry point (preserve)
│   ├── manager.py               # Orchestration (preserve)
│   ├── communicator.py          # SSH/Slurm (preserve)
│   ├── service.py               # Service model (preserve)
│   ├── client.py                # Client model (preserve)
│   ├── storage.py               # Persistence (preserve)
│   ├── command_builders.py      # Command generation (extend for JSONL)
│   ├── health.py                # Health checks (preserve)
│   ├── monitor.py               # Metrics collection (extend)
│   ├── logs.py                  # Log management (extend)
│   ├── reporter.py              # NEW: Report generation + plots
│   ├── statistics.py            # NEW: Percentile/stats helpers
│   └── web/
│       ├── __init__.py
│       └── flask_app.py         # Flask GUI (extend)
├── containers/                   # NEW: Apptainer definitions
│   ├── .gitkeep
│   ├── prometheus.def           # Prometheus container
│   ├── grafana.def              # Grafana container
│   └── pushgateway.def          # Pushgateway container
├── config/                       # NEW: Service configurations
│   ├── prometheus.yml           # Prometheus scrape config
│   └── grafana/
│       ├── provisioning/
│       │   ├── dashboards/default.yaml
│       │   └── datasources/prometheus.yaml
│       └── dashboards/
│           ├── llm-inference.json
│           └── database-benchmark.json
├── examples/                     # Recipe examples (preserve)
│   ├── recipe_vllm.yaml
│   ├── recipe_ollama.yaml
│   ├── recipe_postgres.yaml
│   └── recipe_chroma.yaml
├── results/                      # NEW: Benchmark results (gitignored except .gitkeep)
│   └── .gitkeep
├── reports/                      # NEW: Generated reports (gitignored except .gitkeep)
│   └── .gitkeep
├── logs/                         # NEW: Downloaded logs (gitignored except .gitkeep)
│   └── .gitkeep
├── docs/
│   ├── methodology.md           # NEW: Metrics explanation
│   ├── operations.md            # NEW: How to run on MeluXina
│   └── dataset_index.md         # NEW: Experiment index
├── test/
│   └── test_manager.py
├── ARCHITECTURE.md
├── DEVELOPMENT_PLAN.md          # This file
├── README.md
├── SESSION_SUMMARY.md
└── requirements.txt
```

---

## 4) Data Contracts (Artifacts) — MUST IMPLEMENT

All runs produce artifacts under project root:

### 4.1 Directory layout
- `results/<benchmark_id>/run.json`  
- `results/<benchmark_id>/requests.jsonl`  
- `results/<benchmark_id>/summary.json`  
- `reports/<benchmark_id>/report.md`  
- `reports/<benchmark_id>/report.json`  
- `reports/<benchmark_id>/plots/*.png` (at minimum latency percentiles + throughput)

### 4.2 `run.json` schema (metadata)
Contains:
- `benchmark_id`
- timestamps (`created_at`, `ended_at`)
- git commit (if available)
- recipe content hash + original recipe (embedded or copied)
- service details: type, image, slurm params, hostname/job_id
- client details: num_clients, job_ids
- environment: target cluster name, partition, account
- notes: optional

### 4.3 `requests.jsonl` schema (one line per request)
One JSON object per request.

**Mandatory fields (all services):**
- `timestamp_start` (float epoch seconds) - CRITICAL for throughput calculation
- `timestamp_end` (float epoch seconds) - CRITICAL for latency calculation
- `latency_s` (float) - end minus start
- `success` (bool)
- `service_type` (e.g. `vllm`, `ollama`, `postgres`, `redis`)

**Recommended fields:**
- `request_id` (int)
- `http_status` (int or null)
- `error` (string or null)
- `scenario` (e.g. `offline`/`server`/`single_stream` if applicable)

**Service-specific optional fields:**

For LLM services (vLLM, Ollama):
- `ttft_s` (float or null) — time to first token (if streaming)
- `output_tokens` (int or null)
- `input_tokens` (int or null)
- `tpot_s` (float or null) — time per output token
- `prompt` (string or null) — the prompt used

For Database services (PostgreSQL):
- `operation_type` (string) — "insert", "select", "update", "delete"
- `rows_affected` (int or null)
- `query_type` (string or null) — e.g., "point_lookup", "range_scan", "aggregation"

For Vector DB services (ChromaDB):
- `operation_type` (string) — "insert", "query"
- `num_vectors` (int or null) — vectors inserted or returned
- `dimension` (int or null)

### 4.4 `summary.json` schema (aggregated)
Minimum fields:
- `total_requests`, `successful_requests`, `failed_requests`, `success_rate`
- `latency_s`: `avg`, `min`, `max`, `p50`, `p90`, `p95`, `p99`
- throughput: `requests_per_second`, optional `tokens_per_second`
- for DB: `transactions_per_second` if meaningful
- if available: `ttft_s`: `avg`, `p50`, `p99`

---

## 5) Implementation Strategy (fit existing codebase)

### 5.1 Keep client execution as shell scripts
Your `src/command_builders.py` already generates bash scripts for clients (curl loops, etc.).  
**Keep these working scripts** and extend them minimally so they emit JSON lines to stdout (captured in Slurm logs) AND/OR write to a `requests.jsonl` file.

**Rationale:** fewer runtime dependencies on HPC nodes.

Preservation note:
- Do not replace the client mechanism with a new Python runtime on compute nodes unless strictly required.
- Keep existing human-readable output, but ensure JSONL lines are always present and parseable.

### 5.2 Aggregation happens locally (post-run)
Use Python code on the local machine to:
- fetch/download log outputs (or read stored metrics)
- parse JSONL lines
- compute percentiles
- write `summary.json`
- generate `report.md`
- generate plots (matplotlib) for GUI

### 5.3 GUI uses local artifacts
Flask GUI reads `results/` and `reports/` directories and renders:
- tables + plots
- downloads

Launch options (preserve-first):
- Use `python src/frontend.py --web` as the canonical entrypoint (already implemented).
- Keep `python src/web/flask_app.py` working for direct runs and debugging.

---

## 6) Milestones & Timeline

We assume:
- Month 2 = Jan 2026: implementation
- Month 3 = Feb 2026: experiments + dataset
- Month 4 = Mar 2026: analysis + reporting + defense

### M0 (NOW): Baseline Check (1–2 days)
**Goal:** confirm current baseline works.
- Run at least one existing recipe end-to-end.
- Confirm benchmark IDs persist and GUI loads list.

Acceptance:
- At least one benchmark visible in GUI
- Service deploy + clients run without manual steps

---

## 7) Month 2 (Jan 7–31) — Build MVP: Suite + UX

### Week 1 (Jan 7–13): Standardize Artifacts + JSONL Output
**Tasks**
1. Create directories:
   - `results/`
   - `reports/`
   - ensure they’re git-tracked with `.gitkeep` if needed.

2. Implement artifact writer utilities:
   - helper functions to write `run.json`, `requests.jsonl`, `summary.json`.

3. Update LLM clients (vLLM and/or Ollama) in `src/command_builders.py`:
   - For each request, record start/end in seconds, http status, success.
   - Emit one JSON line per request.
   - Ensure output is valid JSON (escape properly).

4. Update PostgreSQL stress client similarly:
   - For each query/transaction, emit per-operation JSONL.

5. Ensure CLI after run stores:
   - `results/<id>/run.json`
   - raw JSONL extracted from client logs OR written directly by the client job.

Acceptance Criteria
- Running a recipe produces `run.json` and a non-empty `requests.jsonl`.
- JSONL validates (each line parseable JSON).

Notes
- If writing files on compute nodes is hard, parse JSONL from slurm stdout logs and store locally.

### Week 2 (Jan 14–20): Aggregation + Reporting + Plots (Engineer-grade)
**Tasks**
1. Build an aggregator that:
   - loads `requests.jsonl`
   - computes success rate, latency stats, throughput
   - writes `summary.json`

2. Build a report generator that:
   - produces `report.md` (human readable)
   - produces `report.json` (structured)
   - includes:
     - Methodology (scenario, warmup, concurrency model)
     - Reproducibility (recipe hash, git commit, container image, node/partition)
     - Metrics summary table (p50/p95/p99)
     - A “findings” section (template-based suggestions)

3. Plot generation:
   - generate PNG plots into `reports/<id>/plots/`
   - minimum plots:
     - latency percentiles bar chart
     - throughput summary (single number or curve if multiple runs)

Acceptance Criteria
- `python src/frontend.py --report <id>` creates report + plots from existing raw results.
- Summary values match expectations for a small test.

### Buffer Week (Jan 21–27): GUI parity — Metrics + Reports + Logs + Usability Testing
**This week includes time for testing and iteration (e.g., if Week 1–2 slips).**

You already have a Flask UI. Extend it with:

**Tasks**
1. Add GUI pages:
   - `/benchmark/<id>/metrics`
   - `/benchmark/<id>/report`
   - `/benchmark/<id>/logs`

2. Metrics page:
   - load `summary.json`
   - show table: avg/p50/p95/p99 + throughput
   - render plots from `reports/<id>/plots/*.png`

3. Report page:
   - show report markdown (plain preformatted is acceptable)
   - download buttons

4. Logs page:
   - list log files (local downloads preferred)
   - show tail / basic search (regex optional)

5. Add API endpoints for front-end refresh:
   - `/api/benchmark/<id>/summary`
   - `/api/benchmark/<id>/status` (optional; uses stored service/job ids)

6. Usability Testing:
   - Run "fresh user" test: someone not on team installs and runs one recipe + views in GUI
   - Collect feedback on error messages/progress indicators
   - Iterate on UX (e.g., add more guidance text)

Acceptance Criteria
- GUI can open a benchmark and display summary, plots, report, logs.
- No external CDN dependency is required (plots are static PNGs served by Flask).
- Usability test completed with at least 2 feedback points addressed.

### Week 4 (Jan 28–31): Integration + Hardening + Documentation
**Add deliverable for killer features (minimum):**
- Implement at least **KF1 Saturation Finder** and **KF5 One Page summary** in report generation.
- Implement **KF4 Drift/Regression Detection** at least in CLI `--compare`.

**User-friendliness polish:**
- Add `--download-logs <id>` to download all artifacts to local machine
- Ensure all error messages are actionable (not just "failed", but "failed because X, try Y")
- Add progress indicators for long operations

**Prometheus/Grafana preparation (required for easy future integration):**
- Create `containers/` directory with placeholder .def files
- Create `config/` directory with prometheus.yml template
- Create basic Grafana dashboard JSON files (llm-inference.json, database-benchmark.json)
- Add `format_prometheus_metrics()` function to `src/monitor.py`
- Add `/api/benchmark/<id>/metrics/prometheus` endpoint to Flask

**Optional deliverable (only if core is stable):**
- Prototype the optional Prometheus/Grafana launch path behind a feature flag (disabled by default).

**Tasks**
1. End-to-end workflow:
   - run recipe → deploy service → run clients → download logs → build summary → generate report → view in GUI

2. Failure modes:
   - service health check fails → show actionable error message
   - some requests fail → report still generated and indicates failures
   - missing files → GUI shows “not available yet” instead of crashing

3. Documentation:
   - Update README: full CLI + GUI flow
   - Add `docs/methodology.md` (TTFT, percentiles, how to interpret)
   - Add `docs/operations.md` (how to run on MeluXina, expected directories)

Acceptance Criteria
- “Demo runbook” exists (step-by-step).
- A fresh user can run 1 recipe and view results in GUI.

---

## 8) Month 3 (Feb 1–Feb 28) — Benchmarking Experiments & Dataset
### Week 1–2: Run the Benchmark Suite Systematically
**Goal:** produce a coherent dataset for analysis.

LLM suite:
- Concurrency sweep: 1, 2, 4, 8, 16 (as feasible)
- Prompt length sweep: small/medium/large
- Fixed model(s): start with small (`facebook/opt-125m`) then one more realistic model if feasible

Postgres suite:
- Connection sweep: 1, 4, 8, 16
- Read-heavy vs read-write (if supported)

Operational rules:
- Warmup always on
- At least 3 repetitions per config if possible
- Record all recipes and environment metadata

Deliverables:
- raw results under `results/`
- reports under `reports/`
- a dataset index file: `docs/dataset_index.md` linking benchmark IDs to configurations

### Week 3–4: Validate, Re-run, Prepare Comparisons (with Buffer for Reruns)
**Goal:** ensure reproducibility and clean comparisons, and produce analysis artifacts that show differentiation.

Additions:
- Establish a baseline run and perform **KF4 Drift/Regression Detection** checks against it.
- Generate at least one sweep report that includes **KF1 Saturation Finder** output (recommended operating point under SLO).
- Ensure reports include **KF2 Bottleneck Attribution** conclusions grounded in collected metrics.
- If experiments reveal issues (e.g., unstable metrics), use this week as buffer for reruns.

Tasks:
- Identify outliers and rerun
- Establish a “baseline benchmark” for comparisons
- Implement `--compare` output:
  - CLI table comparison
  - GUI comparison page optional (stretch)

Deliverables:
- baseline ID defined in docs
- comparison table(s)
- final validated dataset

## 9) Month 4 (Mar 1–Mar 31) — Evaluation, Reporting, Defense
### Week 1–2: Final Analysis + Final Report
Tasks:
- Summarize key results:
  - saturation points
  - tail latency behavior
  - efficiency metrics
- Create “engineer takeaway” tables:
  - max sustainable concurrency under SLO
  - best config per service

Deliverables:
- Final report (Markdown and optionally PDF)
- Plots suitable for slides
- Updated GUI to display “final dataset overview” (optional)

### Week 3–4: Defense Preparation
Tasks:
- Slides
- Demo scenario prepared:
  - run a small benchmark live (or replay a stored benchmark)
  - show GUI metrics/report/logs
- Final repo cleanup and tagging

Deliverables:
- Slides
- Demo runbook
- Final GitHub release

## 10) Task Breakdown by Module (Implementation Checklist)
### 10.0 Killer Features (Implementation Checklist)

- KF1 Saturation Finder:
  - Add knee/SLO detection for concurrency sweeps
  - Add plot: p99 latency vs concurrency, throughput vs concurrency
  - Add report section: “Recommended Operating Range”
- KF2 Bottleneck Attribution:
  - Implement rule-based classification with evidence strings
  - Emit “Next actions” suggestions (tuning hints)
- KF3 Reproducibility Bundle:
  - Ensure `run.json` includes all required metadata
  - Add rerun workflow (CLI flag if feasible; otherwise documented script)
- KF4 Drift/Regression Detection:
  - Extend `--compare` to flag regressions beyond thresholds
  - Add report appendix for comparisons
- KF5 One Page Summary:
  - Ensure the first page of `report.md` contains decision-oriented metrics and findings

### 10.1 CLI (`src/frontend.py`)
- Add flags:
  - `--report <id>`
  - `--compare <id1> <id2>`
- Ensure `--metrics <id>` triggers collection + summary generation

### 10.2 Client scripts (`src/command_builders.py`)
- Update each “stress” client to print JSONL per request
- Ensure scripts are robust:
  - handle curl failures
  - time measurement works (`date +%s.%N`)
  - avoid locale issues

### 10.3 Metrics (`src/monitor.py`)
- Keep current Slurm `sacct` + `nvidia-smi` collection
- Add local parsing of request JSONL to compute summary stats

### 10.4 Logs (`src/logs.py`)
- Ensure downloading and local caching works
- Provide helpers for GUI to list and read logs

### 10.5 Reporting (`src/reporter.py` new or extend existing)
- Report Markdown + JSON outputs
- Plot generation with matplotlib to PNG

### 10.6 Web GUI (`src/web/flask_app.py`)
- Add pages for metrics, reports, logs
- Provide artifact downloads
- Ensure robust error handling if artifacts missing

### 10.7 Optional Prometheus/Grafana Integration (Add-on)
- Add recipe schema:
  - `monitoring.mode: local|prometheus_grafana`
  - `monitoring.enabled: true|false`
- Implement Slurm-launched monitoring service (Prometheus + Grafana):
  - Keep disabled by default
  - Document SSH tunnel commands and ports
- Integrate into GUI:
  - show monitoring endpoints when enabled
  - never break artifact-based metrics pages

---

## 11) Recommended Implementation Order (Minimize Risk, Preserve-First)

Implement in this order to keep the system working end-to-end at every step:

1. Artifact pipeline first (MVP backbone):
   - Ensure client scripts emit per-request JSONL reliably.
   - Ensure `--metrics <id>` produces `results/<id>/summary.json` (even if partial).
   - Ensure `--report <id>` produces `reports/<id>/report.md` + `reports/<id>/report.json` + PNG plots.

2. Killer features on top of artifacts:
   - KF5 One Page Summary (first section of report).
   - KF1 Saturation Finder for sweep-style experiments.
   - KF4 Drift/Regression detection via `--compare` using `summary.json` deltas.

3. Web GUI parity (read-only pages are enough for MVP):
   - Add metrics/report/logs pages that *only read* the artifacts produced above.
   - Add download links for `run.json`, `summary.json`, `report.md`, `report.json`, plots, and raw JSONL.

4. Optional monitoring preparation (disabled by default):
   - Add the Prometheus-format endpoint and placeholder container/config files.
   - Do not block the artifact-based flow on live monitoring.

## 12) Final Guardrails (Do / Don’t)

Do:
- Keep dependencies minimal:
  - Flask already exists.
  - Add matplotlib only if it is missing and strictly required for PNG plots.
- Fail gracefully:
  - missing artifacts should not crash the GUI; show “not available yet”.
  - partial runs should still produce usable summaries and reports.
- Prefer incremental changes: keep the current CLI entrypoint (`src/frontend.py`) and Flask app.

Don’t:
- Do not rewrite the UI into another framework.
- Do not require Prometheus/Grafana for core grading requirements.
- Do not introduce parallel/duplicate CLI flags when an existing one already covers the capability.

## 13) Repository-Level Definition of Done (Submission Checklist)

- CLI supports (at minimum): run recipe, list, summary, watch, logs, metrics, report, compare, stop.
- GUI supports (at minimum): list benchmarks, benchmark detail, logs view, metrics view (table + plots), report view, artifact downloads.
- For at least two real MeluXina runs (inference + storage):
  - `results/<id>/run.json` + request JSONL exist.
  - `results/<id>/summary.json` exists.
  - `reports/<id>/report.md` exists.
  - Dataset index (`docs/dataset_index.md`) links IDs to recipes/configs.
- At least one report demonstrates KF1 + KF5; at least one comparison demonstrates KF4.