CREATE TABLE research_comparisons (
 id UUID PRIMARY KEY,
 organization_id UUID NOT NULL REFERENCES organizations(id),
 requested_by UUID NOT NULL REFERENCES accounts(id),
 source_job_id UUID NOT NULL REFERENCES simulation_jobs(id),
 comparison_id UUID NOT NULL UNIQUE REFERENCES rainfall_comparisons(id),
 request_key UUID NOT NULL,
 request_hash VARCHAR(64) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 UNIQUE(organization_id,request_key)
);
CREATE INDEX research_comparisons_organization ON research_comparisons(organization_id,created_at);
