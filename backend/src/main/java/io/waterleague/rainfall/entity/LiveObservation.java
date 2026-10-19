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
    BigDecimal pressureHpa,
    BigDecimal windDirectionDeg) {
  public LiveObservation(String stationId, Instant observedAt, BigDecimal fifteenMinuteMm,
      BigDecimal sixtyMinuteMm, BigDecimal dayMm, Boolean rainDetected, BigDecimal oneMinuteMm,
      BigDecimal temperatureC, BigDecimal humidityPercent, BigDecimal windSpeedMs, BigDecimal pressureHpa) {
    this(stationId, observedAt, fifteenMinuteMm, sixtyMinuteMm, dayMm, rainDetected, oneMinuteMm,
        temperatureC, humidityPercent, windSpeedMs, pressureHpa, null);
  }
  public String rainState() {
    if (Boolean.TRUE.equals(rainDetected) || (oneMinuteMm != null && oneMinuteMm.signum() > 0))
      return "WET";
    // 우량계 누적 변화 0은 약한 비의 부재를 입증하지 않는다.
    if (Boolean.FALSE.equals(rainDetected)) return "NO_RAIN_DETECTED";
    return "UNKNOWN";
  }

  public boolean hasRainObservation() {
    return rainDetected != null
        || fifteenMinuteMm != null
        || sixtyMinuteMm != null
        || dayMm != null;
  }

  public boolean complete() {
    return fifteenMinuteMm != null && sixtyMinuteMm != null && dayMm != null;
  }
}
