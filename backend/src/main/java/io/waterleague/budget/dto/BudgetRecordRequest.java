package io.waterleague.budget.dto;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record BudgetRecordRequest(
    UUID ownerId,
    UUID installationId,
    UUID calculationId,
    FacilityType facilityType,
    BigDecimal costKrw,
    Instant installedAt,
    Instant evaluatedThrough) {}
