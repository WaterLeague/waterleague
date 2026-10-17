package io.waterleague.budget.view;

import io.waterleague.budget.entity.BudgetPolicy;
import java.math.BigDecimal;
import java.util.List;

public record BudgetView(
    BudgetPolicy policy,
    BigDecimal allocatedKrw,
    BigDecimal remainingKrw,
    List<DistrictBudget> districts) {
  public record DistrictBudget(
      String districtId, String districtName, BigDecimal allocatedKrw, BigDecimal remainingKrw) {}
}
