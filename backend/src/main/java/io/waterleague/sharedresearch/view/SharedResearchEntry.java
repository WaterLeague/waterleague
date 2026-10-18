package io.waterleague.sharedresearch.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record SharedResearchEntry(
    UUID jobId,
    UUID installationId,
    String districtId,
    String playerName,
    String facilityType,
    BigDecimal areaM2,
    BigDecimal costKrw,
    Instant installedAt,
    Instant removedAt,
    BigDecimal scoreM3,
    BigDecimal playerScoreM3,
    long evaluatedSeconds,
    Instant evaluatedThrough,
    boolean bundleAvailable) {
  @com.fasterxml.jackson.annotation.JsonProperty
  public long evaluatedMinutes() {
    return (evaluatedSeconds + 59) / 60;
  }
}
