CREATE TABLE watershed_experiments (
 id UUID PRIMARY KEY,
 owner_id UUID NOT NULL REFERENCES accounts(id),
 request_key UUID NOT NULL,
 model_hash VARCHAR(64) NOT NULL,
 input_hash VARCHAR(64) NOT NULL,
 placements TEXT NOT NULL,
 state VARCHAR(16) NOT NULL CHECK(state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','REJECTED')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 lease_token UUID,
 lease_until TIMESTAMP WITH TIME ZONE,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 finished_at TIMESTAMP WITH TIME ZONE,
 result TEXT,
 error_code VARCHAR(64),
 UNIQUE(owner_id,request_key)
);
CREATE INDEX watershed_queue ON watershed_experiments(state,created_at);
CREATE INDEX watershed_owner ON watershed_experiments(owner_id,created_at DESC);
