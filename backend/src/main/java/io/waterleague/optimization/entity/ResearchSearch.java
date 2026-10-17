package io.waterleague.optimization.entity;

import java.time.Instant;
import java.util.UUID;

public record ResearchSearch(
    UUID id,
    UUID organizationId,
    UUID requestedBy,
    UUID requestKey,
    String requestHash,
    String modelHash,
    SearchSettings settings,
    String provenance,
    String provenanceHash,
    Instant createdAt) {}
