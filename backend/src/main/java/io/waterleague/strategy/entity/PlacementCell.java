package io.waterleague.strategy.entity;

import java.math.BigDecimal;
import java.util.Set;

public record PlacementCell(
    String id, Set<FacilityType> allowedTypes, BigDecimal maxAreaM2, boolean modelEligible) {
  public PlacementCell {
    allowedTypes = Set.copyOf(allowedTypes);
  }
}
