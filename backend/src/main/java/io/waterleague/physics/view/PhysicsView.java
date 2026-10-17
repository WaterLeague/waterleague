package io.waterleague.physics.view;

import java.time.Instant;
import java.util.UUID;

public record PhysicsView(
    UUID installationId,
    String status,
    String message,
    Instant attemptedAt,
    Instant simulatedThrough,
    Result result) {
  public record Result(
      String stationId,
      String stationName,
      Instant simulationStart,
      Instant simulatedThrough,
      String engineVersion,
      String validationLevel,
      double precipitationM3,
      double infiltrationM3,
      double evaporationM3,
      double runoffM3,
      double storageM3,
      double surfaceDepthMm,
      Double soilMoisture,
      Double storageDepthMm,
      double runoffContinuityPercent,
      String evaporationMethod,
      String initialState,
      String inflowPolicy,
      String areaLimitBasis) {}
}
