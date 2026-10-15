package io.waterleague.league.entity;

import java.time.Instant;
import java.util.UUID;

public record LeagueParticipant(
    UUID leagueId,
    UUID ownerId,
    String displayName,
    String state,
    int revision,
    boolean reviewRequired,
    String rulesHash,
    Instant createdAt,
    Instant updatedAt) {}
