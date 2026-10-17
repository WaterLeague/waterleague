CREATE TABLE shared_research_consents (
 owner_id UUID NOT NULL REFERENCES accounts(id),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 granted BOOLEAN NOT NULL DEFAULT false,
 updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
 PRIMARY KEY(owner_id,organization_id)
);
ALTER TABLE shared_physics_jobs ADD COLUMN artifact_manifest_hash VARCHAR(64);
