package io.waterleague.simulation.entity;

import java.time.Instant;
import java.util.UUID;

public record SimulationJob(
    UUID id,
    UUID versionId,
    UUID ownerId,
    String state,
    String modelHash,
    String inputHash,
    String result,
    String errorCode,
    Instant createdAt) {}
