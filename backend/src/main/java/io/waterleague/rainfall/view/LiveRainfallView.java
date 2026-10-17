package io.waterleague.rainfall.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record LiveRainfallView(
    Instant fetchedAt,
    Instant requestedObservationAt,
    String source,
    String sourceUrl,
    List<Station> districts) {
  public record Station(
      String districtId,
      String districtName,
      String stationId,
      String stationName,
      Instant observedAt,
      Long ageSeconds,
      String status,
      BigDecimal fifteenMinuteMm,
      BigDecimal sixtyMinuteMm,
      BigDecimal dayMm,
      Boolean rainDetected,
      BigDecimal oneMinuteMm,
      String rainState) {}
}
