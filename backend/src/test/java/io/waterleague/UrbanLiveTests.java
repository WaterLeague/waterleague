package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.urban.mapper.UrbanLiveMapper;
import io.waterleague.urban.repository.*;
import io.waterleague.urban.service.UrbanLiveService;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class UrbanLiveTests {
  private final JsonService json = new JsonService(new ObjectMapper());
  private final UrbanLiveMapper mapper = new UrbanLiveMapper(json);
  private static final Instant NOW = Instant.parse("2026-10-19T14:05:00Z");

  private static String population(String name) {
    return """
    [{"hotspot_nm":"%s","time_cd":"22시|현재|10/20 0시|01시","people_interval":"50~60명|100~200명|900~1000명|1000~1200명","people_value":"55|150|950|1100","people_text_list":"과거 인구수|인구수|예상 인구수|예상 인구수","congestion_label_list":"여유|보통|붐빔|붐빔"}]
    """
        .formatted(name);
  }

  private static String traffic(String name, double speed, String at) {
    return """
    {"row":[{"HOTSPOTNM":"%s","ROAD_TRAFFIC_SPD":%s,"ROAD_TRAFFIC_TIME":"%s","SPD":50.0}]}
    """
        .formatted(name, speed, at);
  }

  @Test
  void currentRangeDoesNotUseForecastOrPretendRetrievalIsObservation() {
    var result = mapper.population(population("성수카페거리"), "성수카페거리", NOW);
    assertThat(result.minimum()).isEqualTo(100);
    assertThat(result.maximum()).isEqualTo(200);
    assertThat(result.sourceHourKst()).isEqualTo(23);
    assertThat(result.retrievedAt()).isEqualTo(NOW);
    assertThat(result.validUntil()).isEqualTo(NOW.plusSeconds(300));
    assertThat(result.sourceSha256()).isEqualTo(json.hash(population("성수카페거리")));
  }

  @Test
  void malformedCurrentFutureOldDayAndMismatchAreRejected() {
    String source = population("성수카페거리");
    for (String raw :
        List.of(
            source.replace("현재", "23시"),
            source.replace("22시", "현재"),
            source.replace("10/20", "10/19"),
            source.replace("100~200명", "200~100명"),
            source.replace("|150|", "|NaN|"),
            source.replace("인구수|예상", "예상 인구수|예상"),
            source.replace("성수카페거리", "광화문"),
            "<html>busy</html>"))
      assertThatThrownBy(() -> mapper.population(raw, "성수카페거리", NOW))
          .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> mapper.population(source, "성수카페거리", NOW.plusSeconds(7200)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> mapper.population(source, "성수카페거리", NOW.plusSeconds(86400)))
        .isInstanceOf(DomainException.class);
    assertThat(
            mapper
                .population(source, "성수카페거리", Instant.parse("2026-10-19T15:01:00Z"))
                .sourceHourKst())
        .isEqualTo(23);
  }

  @Test
  void areaSpeedZeroPreservedAndStaleFutureInconsistentRoadDataRejected() {
    var zero = mapper.traffic(traffic("성수카페거리", 0, "2026-10-19 23:00"), "성수카페거리", NOW);
    assertThat(zero.speedKmh()).isZero();
    assertThat(zero.observedAt()).isEqualTo(NOW.minusSeconds(300));
    for (String time : List.of("2026-10-19 22:49", "2026-10-19 23:08", "2026-02-30 23:00"))
      assertThatThrownBy(() -> mapper.traffic(traffic("성수카페거리", 15, time), "성수카페거리", NOW))
          .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () -> mapper.traffic(traffic("다른 장소", 15, "2026-10-19 23:00"), "성수카페거리", NOW))
        .isInstanceOf(DomainException.class);
    String a = traffic("성수카페거리", 15, "2026-10-19 23:00");
    String b = traffic("성수카페거리", 16, "2026-10-19 23:00");
    var rows =
        json.tree(a).path("row").get(0).toString()
            + ","
            + json.tree(b).path("row").get(0).toString();
    assertThatThrownBy(() -> mapper.traffic("{\"row\":[" + rows + "]}", "성수카페거리", NOW))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void catalogValidationOccursBeforeAnyExternalCall() throws Exception {
    var source = mock(SeoulUrbanRepository.class);
    var catalog = new UrbanAreaRepository(json);
    var service = new UrbanLiveService(catalog, source, mapper, Clock.fixed(NOW, ZoneOffset.UTC));
    assertThat(catalog.require("POI001").name()).isNotBlank();
    for (var ids :
        List.of(
            List.<String>of(),
            List.of("https://attacker.invalid"),
            List.of("POI001", "POI001"),
            List.of("POI001", "POI002", "POI003", "POI004", "POI005", "POI006", "POI007")))
      assertThatThrownBy(() -> service.latest(ids)).isInstanceOf(DomainException.class);
    verifyNoInteractions(source);
  }

  @Test
  void failedTrafficDoesNotDiscardPopulationAndCacheAvoidsRepeatedRequests() throws Exception {
    var source = mock(SeoulUrbanRepository.class);
    var catalog = new UrbanAreaRepository(json);
    String name = catalog.require("POI001").name();
    when(source.population(name)).thenReturn(population(name));
    when(source.traffic(name)).thenThrow(new DomainException(ErrorCode.URBAN_UNAVAILABLE));
    var service = new UrbanLiveService(catalog, source, mapper, Clock.fixed(NOW, ZoneOffset.UTC));
    var result = service.latest(List.of("POI001")).places().getFirst();
    assertThat(result.population()).isNotNull();
    assertThat(result.traffic()).isNull();
    assertThat(result.trafficStatus()).isEqualTo("URBAN_UNAVAILABLE");
    assertThat(service.latest(List.of("POI001")).places().getFirst()).isEqualTo(result);
    verify(source, times(1)).population(name);
    verify(source, times(1)).traffic(name);
  }

  @Test
  void simultaneousRequestsShareOneFetchAndSixAreasDoNotAlwaysDropTwo() throws Exception {
    var source = mock(SeoulUrbanRepository.class);
    var catalog = new UrbanAreaRepository(json);
    when(source.population(anyString()))
        .thenAnswer(
            a -> {
              Thread.sleep(15);
              return population(a.getArgument(0));
            });
    when(source.traffic(anyString()))
        .thenAnswer(a -> traffic(a.getArgument(0), 15, "2026-10-19 23:00"));
    var service = new UrbanLiveService(catalog, source, mapper, Clock.fixed(NOW, ZoneOffset.UTC));
    var ids = List.of("POI001", "POI002", "POI003", "POI004", "POI005", "POI006");
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var a = pool.submit(() -> service.latest(ids));
      var b = pool.submit(() -> service.latest(ids));
      for (var response : List.of(a.get(), b.get()))
        assertThat(response.places())
            .allSatisfy(
                p -> {
                  assertThat(p.population()).isNotNull();
                  assertThat(p.traffic()).isNotNull();
                });
    }
    verify(source, times(6)).population(anyString());
    verify(source, times(6)).traffic(anyString());
  }
}
