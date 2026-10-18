package io.waterleague.weekly.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public record SiteScorePage(List<InstallationScore> installations, UUID nextAfterId) {
  public record InstallationScore(
      UUID id,
      UUID ownerId,
      String ownerName,
      String facilityType,
      BigDecimal areaM2,
      Instant installedAt,
      Instant seasonEndsAt,
      BigDecimal scoreM3,
      long evaluatedSeconds,
      Instant evaluatedThrough) {
    @com.fasterxml.jackson.annotation.JsonProperty
    public long evaluatedMinutes() {
      return (evaluatedSeconds + 59) / 60;
    }
  }
}
