package io.waterleague.rainfall.entity;

import java.math.BigDecimal;
import java.time.Instant;

public record LiveObservation(
    String stationId,
    Instant observedAt,
    BigDecimal fifteenMinuteMm,
    BigDecimal sixtyMinuteMm,
    BigDecimal dayMm,
    Boolean rainDetected,
    BigDecimal oneMinuteMm,
    BigDecimal temperatureC,
    BigDecimal humidityPercent,
    BigDecimal windSpeedMs,
    BigDecimal pressureHpa) {
  public String rainState() {
    if (Boolean.TRUE.equals(rainDetected) || (oneMinuteMm != null && oneMinuteMm.signum() > 0))
      return "WET";
    if (Boolean.FALSE.equals(rainDetected) || oneMinuteMm != null) return "NO_RAIN_DETECTED";
    return "UNKNOWN";
  }

  public boolean complete() {
    return fifteenMinuteMm != null && sixtyMinuteMm != null && dayMm != null;
  }
}
