# Source viability checklist

## Purpose

Every new source must pass a viability check before any integration work starts.

This prevents spending engineering time on sources that do not provide stable, machine-readable, matchable, and legally usable data.

## Source types

### Paper source

A source that provides paper-level metadata and may contribute to canonical paper identity.

Examples:

- arXiv
- OpenAlex
- Semantic Scholar
- Crossref
- OpenReview
- ACL Anthology
- PubMed
- bioRxiv
- medRxiv

### Artifact source

A source that provides artifacts linked to papers, but should not be treated as paper-level truth.

Examples:

- GitHub
- Hugging Face Hub
- archived Papers with Code dumps

Artifact sources may enrich:

- repo_url
- code_links
- dataset_links
- model_links
- has_code_link
- has_dataset_link
- has_model_link
- artifact tags

They must not override bibliographic truth fields such as title, venue, journal, publisher, publication_type, citation counts, or references.

### Signal source

A source that provides discovery, popularity, trending, or ranking signals.

Examples:

- Hugging Face Trending Papers
- GitHub stars/trending
- news/social signals

Signal sources must not be merged into canonical truth directly.

## Required viability questions

For every new source, answer:

1. Is the source alive and reachable?
2. Does it provide API, dump, or stable machine-readable data?
3. Does it return JSON/XML/BibTeX/structured records, not HTML-only UI?
4. Can we fetch at least 10-20 real records?
5. Does it expose identifiers useful for matching?
   - DOI
   - arXiv id
   - PMID
   - OpenReview id
   - ACL Anthology id
   - title
   - authors
   - year
6. What is the source type?
   - paper
   - artifact
   - signal
7. What is the stable access mode?
   - live API
   - bulk dump
   - Git repository metadata
   - RSS/feed
   - package client
8. Are there auth requirements?
9. Are there rate limits?
10. Are there license/usage constraints?
11. What are likely false-positive risks?
12. Should the source be:
   - stable
   - candidate-only
   - experimental
   - blocked
   - archived

## Viability verdicts

### viable

The source is reachable, structured, matchable, and safe enough for candidate integration.

### partial

The source is reachable but has limitations: weak identifiers, auth/rate-limit risk, unstable schema, or only partial metadata.

### blocked

The source should not be integrated now.

### archived

The source was previously attempted or used, but is not active.

## Required onboarding flow

1. Add source candidate to `configs/source_viability.yaml`.
2. Run `python -m scripts.validation.check_source_viability --source <name>`.
3. Review report.
4. If viable, create a source contract/mapping note.
5. Implement candidate ingestor only after real-data smoke succeeds.
6. Run source-level audit.
7. Only then consider reconcile/export integration.