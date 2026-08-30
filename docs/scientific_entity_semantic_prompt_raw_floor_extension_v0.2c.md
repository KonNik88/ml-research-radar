# Scientific Entity Semantic Prompt Raw-Floor Extension v0.2c

Status: **completed / development raw-floor hypothesis passed / candidate frozen after downstream comparison**

## Purpose

v0.2a materially improved semantic type disambiguation but lost recall under the
inherited v0.1 source-field thresholds. v0.2b then searched 35 source-field policies
inside the existing raw score floor `0.50`.

The v0.2b selected policy was:

```text
title = 0.50
abstract = 0.625
combined-72 exact F1 = 0.398654
consumed-48 exact F1 = 0.396453
```

It preserved the frozen semantic guardrails but missed the consumed-48 exact-F1
floor `0.396882` by `0.000429`. The selected title threshold was exactly the lowest
score observable in the v0.2a raw evidence.

The v0.2b landscape also separated title and abstract effects:

```text
lower abstract threshold:
recall/F1 improve
method -> task confusion rises above the frozen semantic cap

lower title threshold at abstract=0.625:
recall/F1 improve
observed semantic-confusion counts remain stable
search reaches raw title floor 0.50
```

v0.2c therefore asks one narrower question:

> Does extending raw evidence below `0.50` recover enough additional title mentions
> to pass the frozen development gate while preserving semantic safety?

## Controlled change

The only intended inference change is:

```text
raw inference threshold: 0.50 -> 0.40
```

The extractor identity must change because the runtime config changes.

Everything else remains fixed relative to v0.2a:

```text
model = gliner-community/gliner_small-v2.5
revision = f227d3cd637bd4e6757ae143935316d062393341
model artifact = unchanged
semantic prompts = exactly v0.2a
entity types = task / method / dataset / metric / model / domain
windowing = 320 / 64
development papers = same consumed 72
reference/evaluation semantics = unchanged
```

The contract slice itself does not run inference.

## Raw build boundary

The new raw build will use the existing bounded GLiNER builder on exactly the same
72-paper development package:

```text
scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z
```

The candidate runtime config is:

```text
configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml
```

The raw score floor is inclusively frozen at `0.40` before inference.

## Bounded policy search after raw build

v0.2c does not reopen the two-dimensional v0.2b search.

Primary search dimension:

```text
title threshold:
0.400
0.425
0.450
0.475
0.500
```

Abstract threshold remains fixed:

```text
abstract = 0.625
```

Total primary policies:

```text
5
```

This preserves the evidence-backed v0.2b finding that lower abstract thresholds
recover F1 at the cost of violating the frozen `method -> task` semantic guardrail.

## Semantic-safe eligibility

The v0.2b guardrails are retained exactly:

```text
model -> method <= 43
method -> task <= 25
total type mismatches <= 150
method semantic sink <= 74
maximum any predicted-type mismatch sink <= 74
```

No guardrail is relaxed after the v0.2b result.

## Selection

Among semantic-safe trials only:

1. maximize combined-72 exact F1;
2. tie-break by combined-72 relaxed F1;
3. then combined-72 exact recall;
4. then prefer the stricter title threshold;
5. then deterministic trial ID.

## Development decision gate

A selected policy is promising only if all hard conditions pass:

```text
consumed-48 exact F1 >= 0.396882
combined-72 exact F1 >= 0.398654
semantic guardrails = PASS
```

The desirable consumed-48 relaxed-F1 signal is:

```text
>= 0.419252
```

The combined-development floor is intentionally raised to the already-observed
v0.2b selected value rather than falling back to the older v0.2a gate.

A selected title threshold equal to the new raw floor `0.40` must be flagged as a
possible remaining floor-binding condition before any fresh held-out set is spent.

## Safety boundary

```text
contract model inference = false
contract threshold search = false
prompt changes = false
model changes = false
fresh held-out consumption = false
canonical mutation = false
reconcile input = false
production extractor selection = false
full-corpus build authorization = false
publication = false
```

A fresh disjoint prediction-blind held-out sample remains reserved for a later
frozen promising v0.2 candidate.

## Next slice

After this contract passes strict validation:

```text
bounded raw GLiNER inference at threshold 0.40
on the existing 72 development papers
```

After raw-build validation:

```text
deterministic five-trial title-threshold search
at fixed abstract threshold 0.625
```


## Executed raw-build result

```text
build_id = scientific-entity-gliner-small-v2.5-v0.1-20260830T100756992945Z
raw floor = 0.40
documents = 72
raw predictions = 1762
delta vs v0.2a raw build = +332
strict build validation = 91 / 91
```

All `1430 / 1430` v0.2a mention IDs were preserved with identical scores; no baseline mention was lost. One new title `method` mention, `Transfer Learning`, appeared at score exactly `0.50`. The downstream five-trial calibration selected `title=0.45 / abstract=0.625`, so the new `0.40` floor is not binding. Independent acceptance still requires a new disjoint prediction-blind held-out sample.
