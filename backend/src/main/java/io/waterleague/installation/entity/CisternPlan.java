package io.waterleague.installation.entity;

import java.time.Instant;
import java.util.UUID;

public record CisternPlan(
    UUID id, UUID ownerId, String inputHash, String snapshot, Instant createdAt) {}
