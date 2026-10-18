package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.rainfall.entity.*;
import io.waterleague.rainfall.mapper.KmaPresentWeatherMapper;
import io.waterleague.rainfall.service.RainSignalService;
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class PresentWeatherTests {
  private static final Instant AT = Instant.parse("2026-10-18T09:48:00Z");

  private static String text(String lines) {
    return "#START7777\n# TM, STN, LON, LAT, S, N, WW1, NN1\n" + lines + "\n#7777END\n";
  }

  @Test
  void drizzleWithZeroGaugeStartsRainAndLaterClearObservationStopsIt() {
    var drizzle =
        KmaPresentWeatherMapper.parse(
                text("202610181848, 108, 126.96579742, 37.57141876, 2, 1, 51, 1"), AT)
            .get("108");
    var zero =
        new LiveObservation(
            "108",
            AT,
            BigDecimal.ZERO,
            BigDecimal.ONE,
            BigDecimal.TEN,
            null,
            BigDecimal.ZERO,
            null,
            null,
            null,
            null);
    var signal = RainSignalService.choose(zero, drizzle, AT.plusSeconds(120));
    assertThat(signal.state()).isEqualTo("WET");
    assertThat(signal.evidence()).isEqualTo("AWS_PRESENT_WEATHER");
    assertThat(signal.weatherCode()).isEqualTo(51);
    assertThat(zero.oneMinuteMm()).isZero();
    var clear = new PresentWeather("108", AT.plusSeconds(60), 0);
    assertThat(RainSignalService.choose(zero, clear, AT.plusSeconds(120)).state())
        .isEqualTo("NO_RAIN_DETECTED");
    assertThat(RainSignalService.choose(zero, drizzle, AT.plusSeconds(301)).state())
        .isEqualTo("UNKNOWN");
    assertThat(RainSignalService.choose(zero, drizzle, AT.minusSeconds(1)).state())
        .isEqualTo("UNKNOWN");
  }

  @Test
  void selectsRealPreviousTimeAndSeparatesSnowUnknownAndDeviceConflict() {
    var rows =
        KmaPresentWeatherMapper.parse(
            text(
                "202610181847, 108, 126.96, 37.57, 2, 1, 51, 1,=\n"
                    + "202610181848, 108, 126.96, 37.57, 2, 0\n"
                    + "202610181848, 400, 127.08, 37.49, 2, 1, 72, 1\n"
                    + "202610181848, 540, 126.89, 37.63, 1, 1, 0, 1\n"
                    + "202610181848, 540, 126.89, 37.63, 2, 1, 61, 1"),
            AT);
    assertThat(rows.get("108").observedAt()).isEqualTo(AT.minusSeconds(60));
    assertThat(rows.get("400").rainState()).isEqualTo("SNOW");
    assertThat(rows.get("540").rainState()).isEqualTo("UNKNOWN");
    assertThat(rows).doesNotContainKey("421");
  }

  @Test
  void rejectsAggregatedWindowDuplicatesAndInvalidCoordinates() {
    String row = "202610181848, 108, 126.96, 37.57, 2, 1, 51, 1";
    for (String invalid :
        new String[] {
          row.replace("51, 1", "51, 60"),
          row + "\n" + row,
          row.replace("126.96", "NaN"),
          row.replace("181848", "181849"),
          row.replace("181848", "181843")
        })
      assertThatThrownBy(() -> KmaPresentWeatherMapper.parse(text(invalid), AT))
          .isInstanceOf(DomainException.class);
  }
}
