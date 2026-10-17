package io.waterleague.optimization.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record ResearchCandidate(
    UUID id,
    UUID searchId,
    SearchArm arm,
    int ordinal,
    String placements,
    String modelHash,
    String inputHash,
    BigDecimal cost,
    String state,
    String result,
    String errorCode,
    Instant createdAt,
    Instant finishedAt) {}
