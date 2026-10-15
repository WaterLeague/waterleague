CREATE TABLE leagues (
 id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
 creator_id UUID NOT NULL REFERENCES accounts(id), revision INT NOT NULL CHECK(revision>0),
 state VARCHAR(16) NOT NULL CHECK(state IN ('DRAFT','PUBLISHED','CANCELLED')),
 title VARCHAR(100) NOT NULL, question VARCHAR(2000) NOT NULL,
 opens_at TIMESTAMP WITH TIME ZONE NOT NULL, closes_at TIMESTAMP WITH TIME ZONE NOT NULL,
 model_hash VARCHAR(64) NOT NULL, model_source TEXT NOT NULL,
 rules TEXT NOT NULL, rules_hash VARCHAR(64) NOT NULL,
 execution_hash VARCHAR(64), published_at TIMESTAMP WITH TIME ZONE,
 cancellation_reason VARCHAR(500), created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 CHECK(closes_at>opens_at), CHECK(state='DRAFT' OR published_at IS NOT NULL)
);
CREATE INDEX leagues_public ON leagues(state,closes_at);
CREATE INDEX leagues_organization ON leagues(organization_id,created_at);
CREATE TABLE league_submissions (
 id UUID PRIMARY KEY, league_id UUID NOT NULL REFERENCES leagues(id),
 job_id UUID NOT NULL REFERENCES simulation_jobs(id), owner_id UUID NOT NULL REFERENCES accounts(id),
 score NUMERIC(16,8) NOT NULL, cost NUMERIC(14,2) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL, UNIQUE(league_id,job_id)
);
CREATE INDEX league_submissions_owner ON league_submissions(league_id,owner_id);
