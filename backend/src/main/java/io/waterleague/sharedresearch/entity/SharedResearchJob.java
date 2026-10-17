package io.waterleague.sharedresearch.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record SharedResearchJob(
    UUID id,
    UUID leaseToken,
    UUID ownerId,
    UUID installationId,
    String districtId,
    String cellId,
    String siteModelHash,
    String facilityType,
    BigDecimal areaM2,
    BigDecimal costKrw,
    String playerName,
    Instant installedAt,
    Instant removedAt,
    Instant simulationStart,
    Instant simulatedThrough,
    String inputHash,
    String manifestHash,
    String result) {}
