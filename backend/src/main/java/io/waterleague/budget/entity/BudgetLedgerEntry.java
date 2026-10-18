package io.waterleague.budget.entity;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record BudgetLedgerEntry(
    long id,
    UUID installationId,
    String programId,
    FacilityType facilityType,
    String eventType,
    BigDecimal amountKrw,
    Instant effectiveAt,
    Instant recordedAt,
    String provenance,
    String accountingVersion,
    String sourceBudgetPolicy) {}
