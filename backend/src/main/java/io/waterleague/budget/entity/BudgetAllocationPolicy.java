package io.waterleague.budget.entity;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.List;

public record BudgetAllocationPolicy(
    String version, String budgetRuleVersion, List<Program> programs, List<Facility> facilities) {
  public record Program(String id, String name, BigDecimal limitKrw, String sourceSha256) {}

  public record Facility(FacilityType facilityType, String programId, BigDecimal limitKrw) {}
}
