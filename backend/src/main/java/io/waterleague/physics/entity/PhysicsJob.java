package io.waterleague.physics.entity;

import java.time.Instant;
import java.util.UUID;

public record PhysicsJob(
    UUID id,
    String state,
    Instant createdAt,
    Instant leaseUntil,
    Instant finishedAt,
    Instant requestedThrough,
    String result,
    String errorCode) {}
