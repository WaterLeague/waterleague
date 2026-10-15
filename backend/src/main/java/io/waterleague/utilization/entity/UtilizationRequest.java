package io.waterleague.utilization.entity;

import java.time.Instant;
import java.util.UUID;

public record UtilizationRequest(
    UUID id,
    UUID jobId,
    UUID versionId,
    String modelHash,
    UUID ownerId,
    UUID organizationId,
    String organizationName,
    UUID requestedBy,
    UUID requestKey,
    String title,
    String purpose,
    String policyVersion,
    String termsHash,
    String state,
    int revision,
    Instant createdAt,
    Instant updatedAt) {}
