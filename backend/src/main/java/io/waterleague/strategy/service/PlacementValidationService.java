package io.waterleague.strategy.service;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.exception.PlacementException;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class PlacementValidationService {
  public BigDecimal validate(
      List<Placement> placements,
      Map<String, PlacementCell> cells,
      Map<FacilityType, BigDecimal> unitCosts,
      BigDecimal budget,
      int maxCount) {
    if (placements == null
        || maxCount < 0
        || placements.size() > maxCount
        || budget == null
        || budget.signum() < 0) fail();
    var seen = new HashSet<String>();
    BigDecimal total = BigDecimal.ZERO;
    for (var placement : placements) {
      if (placement == null
          || placement.cellId() == null
          || placement.facilityType() == null
          || placement.areaM2() == null) fail();
      var cell = cells.get(placement.cellId());
      var area = placement.areaM2();
      if (cell == null
          || !cell.modelEligible()
          || !seen.add(placement.cellId())
          || !cell.allowedTypes().contains(placement.facilityType())
          || area.signum() <= 0
          || area.stripTrailingZeros().scale() > 2
          || area.compareTo(cell.maxAreaM2()) > 0) fail();
      var unitCost = unitCosts.get(placement.facilityType());
      if (unitCost == null || unitCost.signum() <= 0) fail();
      total = total.add(area.multiply(unitCost));
    }
    if (total.compareTo(budget) > 0) throw new PlacementException(ErrorCode.BUDGET_EXCEEDED);
    return total;
  }

  private void fail() {
    throw new PlacementException(ErrorCode.PLACEMENT_INVALID);
  }
}
