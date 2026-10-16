# H2 v0.3 production closure

## Purpose

This slice closes the H2 v0.3 production lifecycle after controlled promotion and strict post-promotion validation.

It is an immutable milestone record. It does **not** run model inference, revise thresholds or policy, mutate the candidate, mutate canonical truth, replace trusted latest, or authorize publication.

## Preconditions

The closure requires an exact chain:

1. immutable H2 production promotion decision;
2. exact controlled production-latest promotion record;
3. current trusted `latest.json` equal byte-for-byte to the installed pointer from that promotion;
4. trusted target still present with the authorized SHA-256 and exact line count;
5. rollback path still ready.

## Closure semantics

A successful closure records that:

- H2 v0.3 is the active trusted Scientific Entity production baseline;
- the exact trusted target contains 846264 mentions and 33469 bounded H2 overrides;
- the candidate and canonical truth were not mutated by promotion;
- H2 v0.3 is closed to further tuning;
- the historical production-audit reference is evidence only and must not become tuning data;
- later quality work requires a new version/cycle;
- the next quality stage must use a fresh prediction-blind full-NER coverage sample.

## Safe execution

PLAN is read-only and revalidates the exact parent artifacts and trusted target.

EXECUTE writes only a new immutable closure package under:

`data/entities/scientific_entity_semantic_typer_h2_production_closure/v0.3/<closure_id>`

It never changes `data/entities/scientific_entity_production/v0.3/latest.json`.

## Next stage

After strict closure validation, design a separate prediction-blind full-NER coverage audit over whole title/abstract fields. The prior 240-case H2 production audit remains historical production evidence and is not reused for tuning.
