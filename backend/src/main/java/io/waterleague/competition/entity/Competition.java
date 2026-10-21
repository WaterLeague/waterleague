package io.waterleague.competition.entity;

import java.time.Instant;
import java.util.UUID;

public record Competition(
    UUID id,
    UUID organizationId,
    UUID createdBy,
    String organizationName,
    String title,
    String description,
    String mode,
    String eventId,
    Instant opensAt,
    Instant closesAt,
    String rules,
    String rulesHash,
    String scorePolicySha256,
    String state) {}
