package io.waterleague.strategy.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record StrategyVersion(
    UUID id,
    UUID strategyId,
    int revision,
    String modelHash,
    String inputHash,
    String placements,
    String events,
    String designNote,
    BigDecimal cost,
    String currency,
    Instant createdAt) {}
