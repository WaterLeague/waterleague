package io.waterleague.installation.view;

import java.math.BigDecimal;
import java.util.*;

public record SiteView(
    String districtId,
    String cellId,
    String name,
    String kind,
    List<List<List<List<Double>>>> polygons,
    List<Double> center,
    double heightM,
    double areaM2,
    BigDecimal maxAreaM2,
    List<String> allowedTypes,
    Map<String, BigDecimal> unitCosts,
    String modelHash,
    List<String> sourceIds,
    String areaLimitBasis,
    String siteEligibility,
    String inflowPolicy,
    tools.jackson.databind.JsonNode costModel,
    String costSourceSha256,
    tools.jackson.databind.JsonNode physicalInputs,
    tools.jackson.databind.JsonNode facilityDesignSet,
    tools.jackson.databind.JsonNode initializationPolicy,
    tools.jackson.databind.JsonNode existingInfrastructure,
    String sourceRole,
    tools.jackson.databind.JsonNode referenceInfrastructure,
    String address,
    io.waterleague.installation.entity.SiteSuitability suitability) {
  public BigDecimal maxAreaFor(io.waterleague.strategy.entity.FacilityType type) {
    String key =
        switch (type) {
          case VEGETATIVE_SWALE -> "swaleDesign";
          case INFILTRATION_TRENCH -> "trenchDesign";
          default -> null;
        };
    if (key == null) return maxAreaM2;
    var limit = physicalInputs.path(key).path("maxAreaM2");
    if (!limit.isNumber() || limit.decimalValue().signum() <= 0)
      throw new io.waterleague.common.exception.DomainException(
          io.waterleague.common.exception.ErrorCode.PLACEMENT_INVALID);
    return limit.decimalValue().min(maxAreaM2);
  }
}
