CREATE TABLE cistern_map_plans (
  id UUID PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES accounts(id),
  input_hash VARCHAR(64) NOT NULL CHECK (input_hash ~ '^[a-f0-9]{64}$'),
  snapshot_text TEXT NOT NULL CHECK (octet_length(snapshot_text) <= 1048576),
  created_at TIMESTAMPTZ NOT NULL,
  deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX cistern_map_plans_active_input
  ON cistern_map_plans(owner_id, input_hash) WHERE deleted_at IS NULL;
CREATE INDEX cistern_map_plans_owner_recent
  ON cistern_map_plans(owner_id, created_at DESC) WHERE deleted_at IS NULL;
