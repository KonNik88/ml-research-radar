ALTER TABLE paper_artifact_links
DROP CONSTRAINT IF EXISTS paper_artifact_links_unique;

ALTER TABLE paper_artifact_links
ADD CONSTRAINT paper_artifact_links_unique
UNIQUE (canonical_id, artifact_id, relation_type);