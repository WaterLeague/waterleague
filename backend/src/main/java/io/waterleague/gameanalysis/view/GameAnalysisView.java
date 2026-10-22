package io.waterleague.gameanalysis.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record GameAnalysisView(
    String scope,
    String scopeId,
    Instant generatedAt,
    String snapshotHash,
    boolean summaryAvailable,
    Facts facts) {
  public record Measure(String key, String label, long count, BigDecimal areaM2) {}

  public record Activity(String day, long count) {}

  public record ScoreGroup(
      String key,
      long count,
      BigDecimal totalM3,
      BigDecimal minimumM3,
      BigDecimal maximumM3,
      long negative,
      long zero,
      long positive) {}

  public record Facts(
      String mode,
      String status,
      long participants,
      long records,
      long scoredRecords,
      List<Measure> facilities,
      List<Measure> districts,
      List<Activity> activity,
      List<ScoreGroup> scoreGroups) {}
}
