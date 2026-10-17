package io.waterleague.optimization.view;

import io.waterleague.optimization.entity.*;
import io.waterleague.strategy.entity.Placement;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import tools.jackson.databind.JsonNode;

public record SearchView(
    UUID id,
    UUID organizationId,
    String requestHash,
    String modelHash,
    String provenanceHash,
    Instant createdAt,
    String validationLevel,
    boolean official,
    SearchGeneration generation,
    BigDecimal sourceBestScore,
    boolean completeComparison,
    List<ArmView> arms,
    List<CandidateView> candidates) {
  public record CandidateView(
      UUID id,
      SearchArm arm,
      int ordinal,
      List<Placement> placements,
      String modelHash,
      String inputHash,
      BigDecimal costKrw,
      String state,
      JsonNode result,
      BigDecimal score,
      String errorCode,
      Instant createdAt,
      Instant finishedAt) {}

  public record ArmView(
      SearchArm arm,
      int total,
      int queued,
      int running,
      int succeeded,
      int failed,
      int rejected,
      BigDecimal bestScore) {}

  public record Summary(
      UUID id,
      String modelHash,
      SearchSettings settings,
      Instant createdAt,
      BigDecimal sourceBestScore,
      boolean completeComparison,
      List<ArmView> arms) {}
}
