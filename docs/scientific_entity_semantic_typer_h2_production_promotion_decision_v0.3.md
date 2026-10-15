# H2 v0.3 production promotion decision

This slice creates one immutable decision authorizing a later **controlled** promotion of the already validated H2 v0.3 full-corpus Scientific Entity candidate.

It consumes only immutable metadata/evidence from:

1. the production candidate-build authorization;
2. the full-corpus candidate manifest/summary/checksum lineage;
3. the frozen prediction-blind human reference;
4. the completed production-audit evaluation whose eleven preregistered hard gates all passed.

The decision is bound to the exact candidate build, candidate fingerprint, materialization fingerprint, canonical snapshot, and `final_mentions.jsonl` SHA-256. It does not re-run semantic inference, tune thresholds, revise policy, mutate candidate data, mutate canonical truth, copy anything to trusted/latest, or authorize publication.

`--execute` writes only an immutable decision package. A later slice must independently verify the authorized `final_mentions.jsonl` SHA-256 immediately before mutation, back up the previous trusted latest state, perform the controlled promotion, and run post-promotion/rollback validation.
