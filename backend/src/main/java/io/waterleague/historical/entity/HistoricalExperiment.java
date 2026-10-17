package io.waterleague.historical.entity;

import java.time.Instant;
import java.util.UUID;

public record HistoricalExperiment(
    UUID id,
    UUID ownerId,
    String districtId,
    String modelHash,
    String inputHash,
    String placements,
    String state,
    UUID leaseToken,
    Instant createdAt,
    String result,
    String errorCode) {}
