package io.waterleague.rainfall.entity;

import java.time.Instant;

public record PresentWeather(String stationId, Instant observedAt, Integer code) {
  public String rainState() {
    if (code == null) return "UNKNOWN";
    if ((code >= 40 && code <= 42) || (code >= 50 && code <= 68)) return "WET";
    if (code >= 71 && code <= 76) return "SNOW";
    if (code <= 2 || code == 4 || code == 10 || code == 30) return "NO_RAIN_DETECTED";
    return "UNKNOWN";
  }
}
