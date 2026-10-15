package io.waterleague.analysis.entity;

import java.time.Instant;
import java.util.UUID;

public record ResearchComparison(
    UUID id,
    UUID organizationId,
    UUID requestedBy,
    UUID sourceJobId,
    UUID comparisonId,
    UUID requestKey,
    String requestHash,
    String title,
    Instant createdAt) {}
