CREATE TABLE shared_physics_jobs (
 id UUID PRIMARY KEY,
 installation_id UUID NOT NULL REFERENCES shared_installations(id),
 simulation_start TIMESTAMP WITH TIME ZONE NOT NULL,
 requested_through TIMESTAMP WITH TIME ZONE NOT NULL,
 state VARCHAR(16) NOT NULL CHECK(state IN ('RUNNING','SUCCEEDED','FAILED')),
 lease_token UUID NOT NULL,
 lease_until TIMESTAMP WITH TIME ZONE,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 finished_at TIMESTAMP WITH TIME ZONE,
 input_hash VARCHAR(64),
 result TEXT,
 error_code VARCHAR(64),
 CHECK(requested_through>simulation_start),
 CHECK((state='RUNNING' AND lease_until IS NOT NULL AND finished_at IS NULL)
    OR (state<>'RUNNING' AND lease_until IS NULL AND finished_at IS NOT NULL)),
 CHECK(state<>'SUCCEEDED' OR (input_hash IS NOT NULL AND result IS NOT NULL AND error_code IS NULL))
);
CREATE INDEX shared_physics_installation ON shared_physics_jobs(installation_id,created_at DESC);
CREATE INDEX shared_physics_coverage ON shared_physics_jobs(installation_id,state,requested_through DESC);
