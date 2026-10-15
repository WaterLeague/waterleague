ALTER TABLE leagues ADD COLUMN access_mode VARCHAR(10) NOT NULL DEFAULT 'PUBLIC'
 CHECK(access_mode IN ('PUBLIC','INVITE'));
CREATE INDEX leagues_access ON leagues(access_mode,state,created_at);
CREATE TABLE league_participants (
 league_id UUID NOT NULL REFERENCES leagues(id), owner_id UUID NOT NULL REFERENCES accounts(id),
 state VARCHAR(12) NOT NULL CHECK(state IN ('PENDING','APPROVED','REJECTED','WITHDRAWN')),
 review_required BOOLEAN NOT NULL DEFAULT false,
 revision INT NOT NULL CHECK(revision>0), rules_hash VARCHAR(64) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL, updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
 PRIMARY KEY(league_id,owner_id)
);
CREATE INDEX league_participants_owner ON league_participants(owner_id,updated_at);
CREATE TABLE league_participant_events (
 id UUID PRIMARY KEY, league_id UUID NOT NULL, owner_id UUID NOT NULL,
 actor_id UUID NOT NULL REFERENCES accounts(id), revision INT NOT NULL,
 state VARCHAR(12) NOT NULL CHECK(state IN ('PENDING','APPROVED','REJECTED','WITHDRAWN')),
 reason VARCHAR(500) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 FOREIGN KEY(league_id,owner_id) REFERENCES league_participants(league_id,owner_id),
 UNIQUE(league_id,owner_id,revision)
);
CREATE TABLE league_invitations (
 league_id UUID PRIMARY KEY REFERENCES leagues(id), token_hash VARCHAR(64) NOT NULL UNIQUE,
 expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE TABLE league_teams (
 id UUID PRIMARY KEY, league_id UUID NOT NULL REFERENCES leagues(id),
 captain_id UUID NOT NULL, name VARCHAR(60) NOT NULL, token_hash VARCHAR(64) UNIQUE,
 frozen_at TIMESTAMP WITH TIME ZONE, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 FOREIGN KEY(league_id,captain_id) REFERENCES league_participants(league_id,owner_id),
 UNIQUE(league_id,id), UNIQUE(league_id,name)
);
CREATE TABLE league_team_members (
 league_id UUID NOT NULL, team_id UUID NOT NULL, owner_id UUID NOT NULL,
 joined_at TIMESTAMP WITH TIME ZONE NOT NULL,
 PRIMARY KEY(league_id,owner_id),
 FOREIGN KEY(league_id,owner_id) REFERENCES league_participants(league_id,owner_id),
 FOREIGN KEY(league_id,team_id) REFERENCES league_teams(league_id,id)
);
CREATE INDEX league_team_roster ON league_team_members(league_id,team_id);
ALTER TABLE league_submissions ADD COLUMN team_id UUID;
ALTER TABLE league_submissions ADD CONSTRAINT league_submission_team
 FOREIGN KEY(league_id,team_id) REFERENCES league_teams(league_id,id);
CREATE INDEX league_submissions_team ON league_submissions(league_id,team_id);
