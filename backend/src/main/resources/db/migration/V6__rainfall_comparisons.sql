CREATE TABLE rainfall_comparisons (
 id UUID PRIMARY KEY,
 owner_id UUID NOT NULL REFERENCES accounts(id),
 source_version_id UUID NOT NULL REFERENCES strategy_versions(id),
 request_key UUID NOT NULL,
 request_hash VARCHAR(64) NOT NULL,
 title VARCHAR(80) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 UNIQUE(owner_id, request_key)
);
CREATE INDEX comparisons_owner_time ON rainfall_comparisons(owner_id, created_at);
CREATE TABLE rainfall_comparison_jobs (
 comparison_id UUID NOT NULL REFERENCES rainfall_comparisons(id),
 ordinal INT NOT NULL CHECK(ordinal BETWEEN 0 AND 2),
 model_hash VARCHAR(64) NOT NULL,
 job_id UUID NOT NULL UNIQUE REFERENCES simulation_jobs(id),
 PRIMARY KEY(comparison_id, ordinal),
 UNIQUE(comparison_id, model_hash)
);
