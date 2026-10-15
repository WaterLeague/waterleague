package io.waterleague.optimization.entity;

import io.waterleague.strategy.entity.*;
import java.math.BigDecimal;
import java.util.*;

public record SearchGeneration(
    int schemaVersion,
    String policy,
    String modelHash,
    SearchSettings settings,
    int requestedCount,
    int uniquePhysicalCount,
    int trainingCount,
    BigDecimal cutoffScore,
    int smoothing,
    List<Integer> binPercentages,
    int drawLimit,
    List<Source> sources,
    List<Distribution> distributions,
    List<ArmSummary> arms,
    List<Candidate> candidates,
    int sharedCandidateCount) {
  public record Source(
      SearchSample sample, String physicalHash, List<Placement> placements, boolean selected) {}

  public record Option(
      String key,
      FacilityType facilityType,
      int percent,
      BigDecimal areaM2,
      BigDecimal costKrw,
      int observedCount,
      int patternWeight) {}

  public record Distribution(String cellId, List<Option> options) {}

  public record Candidate(
      SearchArm arm,
      int ordinal,
      int attempt,
      String inputHash,
      String placementsSource,
      List<Placement> placements,
      BigDecimal costKrw) {}

  public record ArmSummary(
      SearchArm arm, int attempts, int emptyRejected, int sourceRejected, int duplicateRejected) {}
}
