package io.waterleague.comparison.entity;

import java.time.Instant;
import java.util.UUID;

public record RainfallComparison(
    UUID id,
    UUID ownerId,
    UUID sourceVersionId,
    String requestHash,
    String title,
    Instant createdAt) {}
