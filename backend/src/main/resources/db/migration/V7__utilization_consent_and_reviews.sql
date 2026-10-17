CREATE TABLE utilization_requests (
 id UUID PRIMARY KEY,
 job_id UUID NOT NULL REFERENCES simulation_jobs(id),
 version_id UUID NOT NULL REFERENCES strategy_versions(id),
 model_hash VARCHAR(64) NOT NULL,
 owner_id UUID NOT NULL REFERENCES accounts(id),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 requested_by UUID NOT NULL REFERENCES accounts(id),
 request_key UUID NOT NULL,
 title VARCHAR(100) NOT NULL,
 purpose VARCHAR(2000) NOT NULL,
 policy_version VARCHAR(60) NOT NULL,
 terms_hash VARCHAR(64) NOT NULL,
 state VARCHAR(20) NOT NULL CHECK(state IN ('PENDING','GRANTED','DECLINED','REVOKED')),
 revision INT NOT NULL CHECK(revision >= 1),
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
 UNIQUE(organization_id,request_key)
);
CREATE INDEX utilization_owner_page ON utilization_requests(owner_id,created_at,id);
CREATE INDEX utilization_org_page ON utilization_requests(organization_id,created_at,id);
CREATE INDEX utilization_active_job ON utilization_requests(job_id,organization_id,state);
CREATE TABLE utilization_decisions (
 id UUID PRIMARY KEY,
 request_id UUID NOT NULL REFERENCES utilization_requests(id),
 actor_id UUID NOT NULL REFERENCES accounts(id),
 decision VARCHAR(20) NOT NULL CHECK(decision IN ('GRANT','DECLINE','REVOKE')),
 revision INT NOT NULL CHECK(revision >= 2),
 terms_hash VARCHAR(64) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 UNIQUE(request_id,revision)
);
CREATE TABLE strategy_reviews (
 id UUID PRIMARY KEY,
 job_id UUID NOT NULL REFERENCES simulation_jobs(id),
 organization_id UUID NOT NULL REFERENCES organizations(id),
 reviewer_id UUID NOT NULL REFERENCES accounts(id),
 state VARCHAR(30) NOT NULL CHECK(state IN ('CANDIDATE','NEEDS_EVIDENCE','NOT_SELECTED')),
 reason VARCHAR(2000) NOT NULL,
 limitations VARCHAR(2000) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX strategy_reviews_job_org ON strategy_reviews(job_id,organization_id,created_at,id);
