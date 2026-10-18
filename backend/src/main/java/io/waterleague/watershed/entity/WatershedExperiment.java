package io.waterleague.watershed.entity;

import java.time.Instant;
import java.util.UUID;

public record WatershedExperiment(
    UUID id,
    UUID ownerId,
    String modelHash,
    String inputHash,
    String placements,
    String state,
    UUID leaseToken,
    Instant createdAt,
    String result) {}
