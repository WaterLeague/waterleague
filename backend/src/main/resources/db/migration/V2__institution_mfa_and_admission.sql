CREATE TABLE account_mfa (
 account_id UUID PRIMARY KEY REFERENCES accounts(id),
 encrypted_secret VARCHAR(256) NOT NULL,
 last_counter BIGINT NOT NULL DEFAULT -1
);
CREATE TABLE queue_admission (id INT PRIMARY KEY);
INSERT INTO queue_admission(id) VALUES(1);
