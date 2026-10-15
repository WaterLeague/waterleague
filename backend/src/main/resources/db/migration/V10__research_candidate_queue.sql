CREATE TABLE research_searches (
 id UUID PRIMARY KEY,
 organization_id UUID NOT NULL REFERENCES organizations(id),
 requested_by UUID NOT NULL REFERENCES accounts(id),
 request_key UUID NOT NULL,
 request_hash VARCHAR(64) NOT NULL,
 model_hash VARCHAR(64) NOT NULL,
 budget_krw NUMERIC(14,2) NOT NULL CHECK(budget_krw>0 AND budget_krw=FLOOR(budget_krw)),
 seed BIGINT NOT NULL CHECK(seed BETWEEN 0 AND 2147483647),
 top_k INT NOT NULL CHECK(top_k BETWEEN 2 AND 20),
 candidates_per_arm INT NOT NULL CHECK(candidates_per_arm BETWEEN 1 AND 4),
 provenance TEXT NOT NULL,
 provenance_hash VARCHAR(64) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 UNIQUE(organization_id,request_key),
 UNIQUE(id,model_hash)
);
CREATE INDEX research_searches_organization ON research_searches(organization_id,created_at);
CREATE TABLE research_search_sources (
 search_id UUID NOT NULL REFERENCES research_searches(id),
 job_id UUID NOT NULL REFERENCES simulation_jobs(id),
 PRIMARY KEY(search_id,job_id)
);
CREATE INDEX research_search_sources_job ON research_search_sources(job_id);
CREATE TABLE research_candidates (
 id UUID PRIMARY KEY,
 search_id UUID NOT NULL,
 arm VARCHAR(10) NOT NULL CHECK(arm IN ('PATTERN','UNIFORM')),
 ordinal INT NOT NULL CHECK(ordinal BETWEEN 1 AND 4),
 placements TEXT NOT NULL,
 model_hash VARCHAR(64) NOT NULL,
 input_hash VARCHAR(64) NOT NULL,
 cost NUMERIC(14,2) NOT NULL CHECK(cost>=0),
 state VARCHAR(20) NOT NULL CHECK(state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','REJECTED')),
 result TEXT,
 error_code VARCHAR(80),
 lease_token UUID,
 lease_until TIMESTAMP WITH TIME ZONE,
 attempts INT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 finished_at TIMESTAMP WITH TIME ZONE,
 FOREIGN KEY(search_id,model_hash) REFERENCES research_searches(id,model_hash),
 UNIQUE(search_id,arm,ordinal),
 UNIQUE(search_id,arm,input_hash),
 CHECK(state<>'RUNNING' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL)),
 CHECK(state<>'SUCCEEDED' OR result IS NOT NULL)
);
CREATE INDEX research_candidates_queue ON research_candidates(state,created_at,id);
