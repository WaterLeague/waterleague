package io.waterleague.league.view;

import io.waterleague.league.entity.LeagueRules;
import java.time.Instant;
import java.util.UUID;

public record LeagueView(
    UUID id,
    UUID organizationId,
    String organizationName,
    int revision,
    String state,
    String phase,
    String title,
    String question,
    LeagueRules rules,
    String rulesHash,
    String executionHash,
    Instant publishedAt,
    String cancellationReason,
    boolean playable) {}
