package io.waterleague.weekly.entity;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record WeeklyContribution(
    UUID playerId,
    String nickname,
    String districtId,
    BigDecimal scoreM3,
    long evaluatedSeconds,
    long expectedSeconds,
    Instant evaluatedThrough) {
  public long evaluatedMinutes() {
    return (evaluatedSeconds + 59) / 60;
  }

  public long expectedMinutes() {
    return (expectedSeconds + 59) / 60;
  }
}
