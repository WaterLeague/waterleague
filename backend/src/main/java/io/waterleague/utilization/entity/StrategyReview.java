package io.waterleague.utilization.entity;

import java.time.Instant;
import java.util.UUID;

public record StrategyReview(
    UUID id,
    UUID jobId,
    UUID organizationId,
    String organizationName,
    UUID reviewerId,
    String state,
    String reason,
    String limitations,
    Instant createdAt) {}
