package io.waterleague.utilization.view;

import java.time.Instant;
import java.util.UUID;

public record ReviewView(
    UUID id,
    UUID jobId,
    UUID organizationId,
    String organizationName,
    String state,
    String reason,
    String limitations,
    Instant createdAt) {}
