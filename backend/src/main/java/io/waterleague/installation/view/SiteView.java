package io.waterleague.installation.view;

import java.math.BigDecimal;
import java.util.*;

public record SiteView(
    String districtId,
    String cellId,
    String name,
    String kind,
    List<List<Double>> coordinates,
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
    tools.jackson.databind.JsonNode existingInfrastructure) {}
