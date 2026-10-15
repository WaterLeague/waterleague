package io.waterleague.analysis.view;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;

public record PatternAnalysisView(
    String modelHash,
    String method,
    int requestedCount,
    int uniqueInputCount,
    int duplicateInputCount,
    int topK,
    int includedCount,
    BigDecimal cutoffScore,
    List<SelectedDesign> designs,
    List<PlacementFrequency> placements,
    List<FacilityPair> facilityPairs,
    BigDecimal minimumCostKrw,
    BigDecimal maximumCostKrw,
    BigDecimal minimumScore,
    BigDecimal maximumScore,
    List<String> limitations) {
  public record SelectedDesign(
      UUID jobId, String inputHash, String physicalHash, BigDecimal score, BigDecimal costKrw) {}

  public record PlacementFrequency(
      String cellId,
      FacilityType facilityType,
      int designCount,
      BigDecimal frequencyPercent,
      BigDecimal minimumAreaM2,
      BigDecimal maximumAreaM2,
      BigDecimal meanInstalledAreaM2,
      BigDecimal meanAllDesignAreaM2) {}

  public record FacilityPair(
      FacilityType first, FacilityType second, int designCount, BigDecimal frequencyPercent) {}
}
