package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.rainfall.mapper.KmaObservationMapper;
import io.waterleague.rainfall.repository.KmaLiveRepository;
import io.waterleague.rainfall.service.LiveRainfallService;
import java.time.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class LiveRainfallTests {
  private static String row(Instant at, String rainfall) {
    return KmaObservationMapper.TIME.format(at.atZone(KmaObservationMapper.KST))
        + " 421 0 0 0 0 0 0 20 0 "
        + rainfall
        + " 0 5 5 60 1000 1010 10";
  }

  private static String response(String rows) {
    return "#START7777\n# RN-15m RN-60m RN-12H RN-DAY\n" + rows + "\n#7777END\n";
  }

  @Test
  void preservesObservedZeroAndMissingWithoutFilling() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    var zero = KmaObservationMapper.parse(response(row(at, "0")), at).get("421");
    assertThat(zero.fifteenMinuteMm()).isZero();
    assertThat(zero.dayMm()).isEqualByComparingTo("5");
    assertThat(zero.observedAt()).isEqualTo(at);
    assertThat(zero.complete()).isTrue();
    assertThat(zero.temperatureC()).isEqualByComparingTo("20");
    assertThat(zero.humidityPercent()).isEqualByComparingTo("60");
    assertThat(zero.windSpeedMs()).isZero();
    assertThat(zero.windDirectionDeg()).isZero();
    assertThat(zero.pressureHpa()).isEqualByComparingTo("1000");
    var missing = KmaObservationMapper.parse(response(row(at, "-99.9")), at).get("421");
    assertThat(missing.fifteenMinuteMm()).isNull();
    assertThat(missing.complete()).isFalse();
  }

  @Test
  void preservesTenMinuteWindDirectionAndMissingValues() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    String observed = row(at, "0").replace("421 0 0 0 0 0 0 20", "421 0 0 0 0 225 3.5 20");
    var wind = KmaObservationMapper.parse(response(observed), at).get("421");
    assertThat(wind.windDirectionDeg()).isEqualByComparingTo("225");
    assertThat(wind.windSpeedMs()).isEqualByComparingTo("3.5");
    var missing = KmaObservationMapper.parse(response(observed.replace("225 3.5", "-99.9 3.5")), at).get("421");
    assertThat(missing.windDirectionDeg()).isNull();
  }

  @Test
  void preservesMissingWeatherWithoutInvalidatingObservedRain() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    String source =
        row(at, "0")
            .replace("0 20 0", "-99.9 -99.9 0")
            .replace("60 1000 1010 10", "-99.9 -99.9 1010 10");
    var missing = KmaObservationMapper.parse(response(source), at).get("421");
    assertThat(missing.temperatureC()).isNull();
    assertThat(missing.humidityPercent()).isNull();
    assertThat(missing.windSpeedMs()).isNull();
    assertThat(missing.pressureHpa()).isNull();
    assertThat(missing.complete()).isTrue();
    assertThatThrownBy(
            () ->
                KmaObservationMapper.parse(
                    response(row(at, "0").replace("60 1000 1010 10", "101 1000 1010 10")), at))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void rejectsDuplicateWrongTimeAndInvalidValues() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    for (String bad : List.of("-1", "NaN", "Infinity", "5001"))
      assertThatThrownBy(() -> KmaObservationMapper.parse(response(row(at, bad)), at))
          .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> KmaObservationMapper.parse(response(row(at, "0") + "\n" + row(at, "0")), at))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> KmaObservationMapper.parse(response(row(at.minusSeconds(300), "0")), at))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> KmaObservationMapper.parse("invalid provider output", at))
        .isInstanceOf(DomainException.class);
  }

  private static String observed(Instant at, String sensor, String daily) {
    return KmaObservationMapper.TIME.format(at.atZone(KmaObservationMapper.KST))
        + " 421 0 0 0 0 0 0 20 "
        + sensor
        + " 3 8 10 "
        + daily
        + " 60 1000 1010 10";
  }

  @Test
  void rainEffectUsesCurrentSensorOrConsecutiveMinuteNotPastAccumulation() {
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    var wet =
        KmaObservationMapper.parse(
                response(
                    observed(at.minusSeconds(60), "-99.9", "5")
                        + "\n"
                        + observed(at, "-99.9", "5.5")),
                at)
            .get("421");
    assertThat(wet.oneMinuteMm()).isEqualByComparingTo("0.5");
    assertThat(wet.rainState()).isEqualTo("WET");
    var stopped =
        KmaObservationMapper.parse(
                response(observed(at.minusSeconds(60), "0", "5") + "\n" + observed(at, "0", "5")),
                at)
            .get("421");
    assertThat(stopped.sixtyMinuteMm()).isPositive();
    assertThat(stopped.rainState()).isEqualTo("NO_RAIN_DETECTED");
    assertThat(
            KmaObservationMapper.parse(response(observed(at, "1", "-99.9")), at)
                .get("421")
                .rainState())
        .isEqualTo("WET");
    assertThat(
            KmaObservationMapper.parse(response(observed(at, "-99.9", "5")), at)
                .get("421")
                .rainState())
        .isEqualTo("UNKNOWN");
  }

  @Test
  void doesNotInventMinuteRainOnDayResetOrNegativeDifference() {
    for (Instant at :
        List.of(Instant.parse("2026-10-17T15:00:00Z"), Instant.parse("2026-10-17T11:47:00Z"))) {
      var value =
          KmaObservationMapper.parse(
                  response(
                      observed(at.minusSeconds(60), "-99.9", "5")
                          + "\n"
                          + observed(at, "-99.9", "0")),
                  at)
              .get("421");
      assertThat(value.oneMinuteMm()).isNull();
      assertThat(value.rainState()).isEqualTo("UNKNOWN");
    }
    Instant at = Instant.parse("2026-10-17T11:47:00Z");
    assertThatThrownBy(() -> KmaObservationMapper.parse(response(observed(at, "2", "5")), at))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void missingLatestMinuteKeepsPreviousObservationWithItsOriginalTime() {
    Instant at = Instant.parse("2026-10-18T09:45:00Z");
    var value =
        KmaObservationMapper.parse(
                response(
                    observed(at.minusSeconds(120), "-99.9", "5")
                        + "\n"
                        + observed(at.minusSeconds(60), "-99.9", "5.5")
                        + "\n"
                        + observed(at, "-99.9", "-99.9").replace("3 8 10", "-99.9 -99.9 -99.9")),
                at)
            .get("421");
    assertThat(value.observedAt()).isEqualTo(at.minusSeconds(60));
    assertThat(value.oneMinuteMm()).isEqualByComparingTo("0.5");
    assertThat(value.rainState()).isEqualTo("WET");
  }

  @Test
  void zeroIncrementWithoutRainSensorDoesNotClaimDryWeather() {
    Instant at = Instant.parse("2026-10-18T09:45:00Z");
    var value =
        KmaObservationMapper.parse(
                response(observed(at.minusSeconds(60), "-1", "5") + "\n" + observed(at, "-1", "5")),
                at)
            .get("421");
    assertThat(value.oneMinuteMm()).isZero();
    assertThat(value.rainDetected()).isNull();
    assertThat(value.rainState()).isEqualTo("UNKNOWN");
  }

  @Test
  void fetchesEveryRequestAndNeverFallsBackAfterFailure() {
    var source = mock(KmaLiveRepository.class);
    var districts = mock(DistrictRepository.class);
    when(districts.all())
        .thenReturn(
            List.of(
                new io.waterleague.district.entity.District(
                    "2419947", "성동구", "map", "hash", List.of(0.0, 0.0), "421", "성동")));
    when(source.fetch(any()))
        .thenAnswer(call -> response(row(call.getArgument(0), "0")))
        .thenThrow(new DomainException(ErrorCode.RAINFALL_UNAVAILABLE));
    var service = new LiveRainfallService(source, districts);
    assertThat(service.latest().districts().getFirst().status()).isEqualTo("CURRENT");
    assertThatThrownBy(service::latest).isInstanceOf(DomainException.class);
    verify(source, times(2)).fetch(any());
  }
}
