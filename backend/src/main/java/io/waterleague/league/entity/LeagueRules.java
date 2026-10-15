package io.waterleague.league.entity;

import io.waterleague.strategy.entity.FacilityType;
import java.time.Instant;
import java.util.List;

public record LeagueRules(
    int schemaVersion,
    String modelHash,
    String engineRevision,
    String generatorSha256,
    String scoreRule,
    String currency,
    long budget,
    List<FacilityType> allowedTypes,
    int submissionLimit,
    Instant opensAt,
    Instant closesAt,
    String validationLevel,
    boolean official) {}
