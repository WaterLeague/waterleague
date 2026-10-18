package io.waterleague.budget.view;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.List;

public record BudgetAccountingView(
    String version, List<Program> programs, List<Facility> facilities) {
  public record Program(
      String id,
      String name,
      BigDecimal limitKrw,
      BigDecimal allocatedKrw,
      BigDecimal remainingKrw,
      String sourceSha256) {}

  public record Facility(
      FacilityType facilityType,
      String programId,
      BigDecimal limitKrw,
      BigDecimal allocatedKrw,
      BigDecimal availableKrw) {}
}
