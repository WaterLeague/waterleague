package io.waterleague.budget.view;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public record BudgetLedgerView(List<Entry> entries, String nextBeforeId) {
  public record Entry(
      String id,
      UUID installationId,
      String programId,
      FacilityType facilityType,
      String eventType,
      BigDecimal amountKrw,
      Instant effectiveAt,
      Instant recordedAt,
      String provenance,
      String accountingVersion,
      JsonNode sourceBudgetPolicy) {}
}
