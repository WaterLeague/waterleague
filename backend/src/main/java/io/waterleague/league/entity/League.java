package io.waterleague.league.entity;

import java.time.Instant;
import java.util.UUID;

public record League(
    UUID id,
    UUID organizationId,
    String organizationName,
    int revision,
    String state,
    String title,
    String question,
    Instant opensAt,
    Instant closesAt,
    String modelHash,
    String modelSource,
    String rules,
    String rulesHash,
    String executionHash,
    Instant publishedAt,
    String cancellationReason,
    Instant createdAt) {}
