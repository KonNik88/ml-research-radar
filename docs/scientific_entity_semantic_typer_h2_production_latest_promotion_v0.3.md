# H2 v0.3 controlled production-latest promotion

This slice consumes the already validated immutable H2 production promotion decision and promotes exactly one previously validated full-corpus candidate into the trusted Scientific Entity state.

## Trusted-state representation

The production layer uses a small `data/entities/scientific_entity_production/v0.3/latest.json` pointer. The pointer targets the already immutable candidate `final_mentions.jsonl` and binds its exact SHA-256, candidate build ID, H2 fingerprint, materialization fingerprint, canonical snapshot and counts.

This deliberately avoids copying the large JSONL only to rename it `latest`. Promotion changes trust metadata, not candidate bytes.

## Safety

Before any mutation the executor re-validates the promotion decision, re-hashes the actual candidate `final_mentions.jsonl`, verifies its exact authorized SHA and line count, and snapshots the previous trusted-latest pointer state.

If this is the first trusted Scientific Entity promotion, there is no previous pointer to copy. The immutable promotion record therefore stores an explicit `previous_latest_exists=false` bootstrap snapshot; rollback removes the newly created pointer and restores the pre-promotion state of “no trusted latest”. Future promotions store the exact previous pointer bytes and can restore them byte-for-byte.

The trusted pointer is replaced atomically with `os.replace`. Post-promotion validation re-opens the installed pointer, verifies that it is byte-identical to the expected pointer, and re-validates the referenced immutable artifact SHA and line count. Any exception after pointer mutation triggers an immediate in-process rollback before the promotion record is finalized.

The promotion does not mutate canonical truth, candidate artifacts, H2 policy, thresholds, or model outputs, and does not authorize publication.
