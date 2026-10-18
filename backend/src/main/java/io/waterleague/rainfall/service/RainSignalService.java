package io.waterleague.rainfall.service;

import io.waterleague.rainfall.entity.LiveObservation;
import io.waterleague.rainfall.entity.PresentWeather;
import java.time.*;

public final class RainSignalService {
  private RainSignalService() {}

  public record Signal(String state, String evidence, Instant observedAt, Integer weatherCode) {}

  public static Signal choose(LiveObservation rain, PresentWeather weather, Instant now) {
    var sensor = rain != null && fresh(rain.observedAt(), now) ? rain : null;
    var currentWeather = weather != null && fresh(weather.observedAt(), now) ? weather : null;
    boolean knownSensor = sensor != null && !sensor.rainState().equals("UNKNOWN");
    if (currentWeather != null
        && (!knownSensor
            || (!currentWeather.rainState().equals("UNKNOWN")
                && !currentWeather.observedAt().isBefore(sensor.observedAt()))))
      return new Signal(
          currentWeather.rainState(),
          "AWS_PRESENT_WEATHER",
          currentWeather.observedAt(),
          currentWeather.code());
    if (knownSensor)
      return new Signal(
          sensor.rainState(),
          sensor.oneMinuteMm() != null && sensor.oneMinuteMm().signum() > 0
              ? "AWS_MINUTE_INCREMENT"
              : "AWS_RAIN_SENSOR",
          sensor.observedAt(),
          null);
    return new Signal("UNKNOWN", "UNKNOWN", null, null);
  }

  private static boolean fresh(Instant at, Instant now) {
    long age = Duration.between(at, now).toMillis();
    return age >= 0 && age <= 300000;
  }
}
