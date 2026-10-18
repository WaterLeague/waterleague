CREATE TABLE historical_design_revisions (
 owner_id UUID NOT NULL REFERENCES accounts(id),
 event_id VARCHAR(32) NOT NULL,
 revision BIGINT NOT NULL CHECK (revision > 0),
 request_key UUID NOT NULL,
 request_raw TEXT NOT NULL,
 snapshot_raw TEXT NOT NULL,
 snapshot_sha256 VARCHAR(64) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 PRIMARY KEY (owner_id,event_id,revision),
 UNIQUE (owner_id,request_key)
);
