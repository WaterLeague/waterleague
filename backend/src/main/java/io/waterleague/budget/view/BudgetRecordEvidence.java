package io.waterleague.budget.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record BudgetRecordEvidence(
    int schemaVersion,
    UUID calculationId,
    UUID installationId,
    Instant capturedAt,
    Instant evaluatedThrough,
    String status,
    String timeBasis,
    BigDecimal installationCostKrw,
    BigDecimal allocatedAtEvaluationKrw,
    BigDecimal allocatedAtCaptureKrw,
    Instant removedAt,
    List<BudgetLedgerView.Entry> entries) {}
