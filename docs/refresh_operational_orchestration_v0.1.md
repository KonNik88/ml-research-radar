# Refresh Operational Orchestration v0.1

## Document status

```text
status = implemented bounded operational orchestration contract
version = v0.1
recommended_entrypoint = scripts.update.run_refresh_operational_flow
legacy_lower_level_runner = scripts.update.run_refresh_pipeline_v1
canonical_truth_changed_by_contract = false
dataset_publication_changed = false
qdrant_promotion_changed = false
```

## 1. Purpose

This contract turns the validated manual `docs/refresh_runbook_v1.md` sequence
into one phase-based operational entrypoint.

The runner composes existing builders, validators, promotion gates, exports, and
Definition-of-Done checks. It does not copy their business logic and does not
create a second reconciliation implementation.

The paper-level source of truth remains:

```text
data/analytics/reconciled/canonical_documents.jsonl
```

All alignment snapshots, candidates, reports, retrieval indexes, Postgres paper
tables, paper features, ranking samples, paper detail, similar papers, topic
clusters, projections, and API/UI quality reports remain derived or operational
artifacts.

## 2. Entrypoint ownership

Recommended operational entrypoint:

```bat
python -m scripts.update.run_refresh_operational_flow --phase <phase>
```

`run_refresh_pipeline_v1.py` remains supported as a lower-level/legacy runner,
especially for its bounded `--candidate-rehearsal` mode. Its historical full
mode is not the recommended production refresh path after controlled-promotion
and merged-alignment hardening.

The operational runner invokes the legacy candidate rehearsal with `--strict`
so an internal stopped-on-failure result becomes a non-zero child-process exit.
Calls that omit `--strict` keep the previous standalone CLI behavior.

The new runner must use:

```text
scripts.update.run_refresh_controlled_promotion
```

for promotion. It must never invoke `promote_canonical_candidate` directly.

## 3. Public phases

```text
preflight
candidate
promote
core-derived
postgres
discovery-derived
full
```

`alignment-inputs` is an explicit internal step at the beginning of `preflight`,
not a separate public phase in v0.1.

### 3.1 `preflight`

```text
build full merged alignment snapshots
→ strict refresh preflight contract
```

This phase may write alignment-derived snapshots and reports with `--execute`.
It must not create or promote canonical latest.

### 3.2 `candidate`

```text
lower-level candidate rehearsal
→ alignment coverage diagnostics
→ source coverage diagnostics
→ strict promotion readiness
```

The candidate rehearsal may write a timestamped candidate and reports. It must
stop before promotion and all downstream rebuilds.

### 3.3 `promote`

Promotion is a two-command human gate:

```bat
python -m scripts.update.run_refresh_operational_flow --phase promote
python -m scripts.update.run_refresh_operational_flow --phase promote --execute
```

The first command runs the real non-mutating controlled-promotion dry run. The
second command is allowed only when the latest controlled-promotion report:

- is a successful `dry_run`;
- reports `safe_to_execute=true`;
- reports no canonical mutation;
- references the same candidate as promotion readiness;
- is not older than the readiness report or candidate file.

The controlled-promotion child process repeats its own readiness checks during
execute. The orchestration freshness check is an additional human-boundary
guard, not a replacement for the controlled-promotion contract.

### 3.4 `core-derived`

```text
retrieval build
→ retrieval checks
→ post-pass audit
→ known-issues snapshot
→ strict core Definition of Done
```

This phase runs only after accepted canonical promotion. It rebuilds derived
retrieval state and never modifies canonical truth.

### 3.5 `postgres`

```text
pre-export DB smoke
→ replace paper materialization
→ post-export DB smoke
→ strict Definition of Done
```

The runner does not start Docker or Postgres. An unavailable database fails the
first smoke step before `export_postgres_v1 --replace` can run.

`--replace` owns only rebuildable paper/source materialization. Workspace-owned
mutable state such as research collections must remain outside the replacement
boundary.

### 3.6 `discovery-derived`

```text
paper features build/check
→ ranking profiles check
→ fresh bounded ranking sample/check
→ paper detail build/check
→ similar papers build/check
→ topic clusters build/check
→ topic projection build/check
→ Discovery API check
→ Streamlit Discovery UI check
→ strict Discovery Definition of Done
```

The ranking sample is rebuilt before paper detail so that
`--from-latest-ranking-rank 1` never depends on an unrelated stale ranking
report.

### 3.7 `full`

`full` is a complete plan view in v0.1:

```bat
python -m scripts.update.run_refresh_operational_flow --phase full
```

`full --execute` is intentionally fail-closed. A single command must not create
a new candidate, approve it, cross the manual promotion boundary, and continue
to destructive derived replacements.

The executable operational sequence is deliberately phase-by-phase:

```text
preflight --execute
candidate --execute
promote
manual report review
promote --execute
core-derived --execute
postgres --execute
discovery-derived --execute
```

Resume/state-machine behavior may be designed separately after v0.1 has been
used for a real refresh.

## 4. Plan and execute semantics

For every phase except `promote`:

```text
without --execute = write a plan report; run no child command
with --execute    = execute the selected phase
```

For `promote`:

```text
without --execute = execute controlled promotion dry-run
with --execute    = execute controlled promotion after freshness prechecks
```

`--execute` authorizes only the mutation domains declared by the selected
phase. It does not authorize an adjacent phase implicitly.

## 5. Mutation domains

| Phase | Permitted writes | Forbidden writes |
|---|---|---|
| `preflight` | merged alignment inputs, reports | canonical latest, Postgres |
| `candidate` | candidate JSONL, validation reports | canonical latest, Postgres |
| `promote` dry-run | reports | canonical latest, derived rebuilds |
| `promote --execute` | canonical latest through controlled promotion and backup | direct unguarded promotion |
| `core-derived` | retrieval/audit/known-issues artifacts | canonical latest, Postgres |
| `postgres` | rebuildable Postgres paper tables | canonical latest, workspace tables |
| `discovery-derived` | features/ranking/detail/similar/clusters/projection/reports | canonical latest |
| `full` | none in v0.1 | every mutation |

## 6. Stop-on-failure

Child commands are executed sequentially. A non-zero child return code stops
the phase immediately. Later steps are recorded as skipped.

The final DoD commands use `--strict`; therefore `dod_passed=false` becomes a
non-zero process result suitable for orchestration.

Important failure boundaries:

- failed preflight prevents candidate work;
- failed candidate rehearsal prevents coverage/readiness continuation;
- failed readiness prevents promotion;
- missing or stale promotion dry-run prevents promotion execute;
- unavailable Postgres prevents replace export;
- failed Discovery builder/validator prevents later Discovery steps;
- failed strict DoD prevents phase completion.

## 7. Reports

Default report paths:

```text
artifacts/reports/update/run_refresh_operational_flow_latest.json
artifacts/reports/update/run_refresh_operational_flow_latest.md
artifacts/reports/update/history/run_refresh_operational_flow_<timestamp>.json
artifacts/reports/update/history/run_refresh_operational_flow_<timestamp>.md
```

Each report includes:

- phase and mode;
- normalized inputs;
- mutation policy;
- execution prechecks;
- planned steps and exact commands;
- executed steps;
- bounded stdout/stderr tails;
- timings and return codes;
- failed step names;
- stop-on-failure state;
- phase completion and mutation summary.

These reports are operational evidence. They are not canonical truth and are
not reconciliation inputs.

## 8. Intentional v0.1 exclusions

The first operational runner does not include:

- artifact extraction or artifact Postgres rebuild;
- GitHub or Hugging Face live enrichment;
- citation/reference graph rebuild;
- golden-query evaluation;
- collections or comparison regressions;
- Docker lifecycle management;
- automatic rollback;
- retry policy;
- parallel execution;
- Airflow, Prefect, Kafka, Ray, or Kubernetes;
- dataset publication;
- Qdrant promotion;
- model or clustering replacement.

These remain separate opt-in lines until a later bounded design requires them.

## 9. Verification contract

Required smoke coverage includes:

- stable public phase set;
- phase-to-step ordering;
- plan mode without child execution;
- bounded candidate rehearsal without promotion;
- controlled-promotion ownership;
- fresh matching dry-run requirement;
- `full --execute` fail-closed behavior;
- Postgres smoke before replace;
- ranking before detail/similar;
- complete Discovery DoD flags;
- stop at first child failure;
- latest/history report generation with collision-resistant history names;
- strict DoD CLI support.

The runner is safe to merge after focused smoke tests and the existing refresh
regression group pass. A new full 61k refresh is not required merely to merge
the orchestration code; its first real end-to-end acceptance should happen on
the next substantive source refresh.
