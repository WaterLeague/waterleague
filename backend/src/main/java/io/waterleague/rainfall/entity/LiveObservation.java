package io.waterleague.rainfall.entity;

import java.math.BigDecimal;
import java.time.Instant;

public record LiveObservation(
    String stationId,
    Instant observedAt,
    BigDecimal fifteenMinuteMm,
    BigDecimal sixtyMinuteMm,
    BigDecimal dayMm) {
  public boolean complete() {
    return fifteenMinuteMm != null && sixtyMinuteMm != null && dayMm != null;
  }
}
