package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.repository.WatershedCostRepository;
import java.math.BigDecimal;
import java.util.*;
import tools.jackson.databind.JsonNode;

public final class CisternReferenceService {
  private CisternReferenceService() {}

  public static Map<String, Object> snapshot(
      String hash, List<Map<String, Object>> placements, JsonNode source) {
    if (!WatershedCostRepository.CISTERN_HASH.equals(hash))
      throw new DomainException(ErrorCode.CONFLICT);
    var items = new ArrayList<Map<String, Object>>();
    var unit = new BigDecimal(source.path("unitCapacityM3").asString());
    for (var p : placements) {
      if (!"RAINWATER_CISTERN".equals(p.get("facilityType"))) continue;
      var parameters = (JsonNode) p.get("parameters");
      BigDecimal capacity =
          ((BigDecimal) p.get("areaM2"))
              .multiply(parameters.path("storageDepthMm").decimalValue())
              .divide(new BigDecimal("1000"));
      var division = capacity.divideAndRemainder(unit);
      Integer units =
          division[1].signum() == 0
                  && division[0].signum() > 0
                  && division[0].compareTo(new BigDecimal("256")) <= 0
              ? division[0].intValueExact()
              : null;
      var row = new TreeMap<String, Object>();
      row.put("placementId", p.get("id"));
      row.put("capacityM3", capacity);
      row.put("equivalentUnits", units);
      row.put("status", units == null ? "CAPACITY_NOT_MATCHED" : "CAPACITY_EQUIVALENT_ONLY");
      var quotes = new ArrayList<Map<String, Object>>();
      if (units != null) for (var q : source.path("quotes")) quotes.add(quote(q, units, source));
      row.put("quotes", quotes);
      items.add(row);
    }
    if (items.isEmpty()) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var result = new TreeMap<String, Object>();
    result.put("schemaVersion", 1);
    result.put("catalogHash", hash);
    result.put("method", "CAPACITY_EQUIVALENT_QUOTES_NOT_ASSEMBLY_MATCH_V1");
    result.put("unitCapacityM3", unit);
    result.put("items", items);
    result.put("source", source.path("source"));
    result.put("limitations", source.path("limitations"));
    result.put("completeInstalledCostKrw", null);
    result.put("budgetChargedKrw", null);
    return result;
  }

  private static Map<String, Object> quote(JsonNode q, int units, JsonNode source) {
    long total = q.path("totalKrw").asLong() * units;
    long materials = q.path("materialsKrw").asLong() * units;
    var components = new TreeMap<String, Object>();
    long sum = 0;
    for (String name : q.path("components").propertyNames()) {
      var v = q.path("components").path(name);
      Long value = v.isNull() ? null : v.asLong() * units;
      components.put(name, value);
      if (value != null) sum += value;
    }
    if (sum != materials || total < materials) throw new IllegalStateException("이용조 견적 소계 불일치");
    var annual = new TreeMap<String, Long>();
    for (var r : source.path("annualOperation").path("ratesOnInitialCost"))
      annual.put(
          r.path("id").asString(),
          new BigDecimal(r.path("rate").asString())
              .multiply(BigDecimal.valueOf(total))
              .longValueExact());
    var cleaning = source.path("annualOperation").path("cleaning");
    annual.put(
        "CLEANING",
        cleaning.path("costKrw").asLong() * units / cleaning.path("households").asLong());
    return Map.of(
        "id",
        q.path("id").asString(),
        "quotedSubtotalKrw",
        total,
        "materialsKrw",
        materials,
        "components",
        components,
        "unclassifiedDifferenceKrw",
        total - materials,
        "annualComponentsKrw",
        annual,
        "annualEstimateKrw",
        annual.values().stream().mapToLong(Long::longValue).sum());
  }
}
