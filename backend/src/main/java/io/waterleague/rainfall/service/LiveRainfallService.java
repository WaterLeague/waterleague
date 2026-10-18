package io.waterleague.rainfall.service;

import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.rainfall.entity.LiveObservation;
import io.waterleague.rainfall.entity.PresentWeather;
import io.waterleague.rainfall.mapper.KmaObservationMapper;
import io.waterleague.rainfall.mapper.KmaPresentWeatherMapper;
import io.waterleague.rainfall.repository.KmaLiveRepository;
import io.waterleague.rainfall.view.LiveRainfallView;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.concurrent.*;
import org.springframework.stereotype.Service;

@Service
public class LiveRainfallService {
  private final KmaLiveRepository source;
  private final DistrictRepository districts;
  private CompletableFuture<LiveRainfallView> inFlight;

  public LiveRainfallService(KmaLiveRepository source, DistrictRepository districts) {
    this.source = source;
    this.districts = districts;
  }

  public LiveRainfallView latest() {
    CompletableFuture<LiveRainfallView> current;
    boolean leader = false;
    synchronized (this) {
      if (inFlight == null) {
        inFlight = new CompletableFuture<>();
        leader = true;
      }
      current = inFlight;
    }
    if (leader) {
      try {
        current.complete(fetch());
      } catch (Exception e) {
        current.completeExceptionally(e);
      } finally {
        synchronized (this) {
          if (inFlight == current) inFlight = null;
        }
      }
    }
    try {
      return current.join();
    } catch (CompletionException e) {
      if (e.getCause() instanceof DomainException d) throw d;
      throw new DomainException(ErrorCode.RAINFALL_UNAVAILABLE);
    }
  }

  private LiveRainfallView fetch() {
    // 최신 분이 생산 중이면 같은 직접 조회 범위의 이전 유효 관측을 사용한다.
    Instant requested = Instant.now().truncatedTo(ChronoUnit.MINUTES).minusSeconds(60);
    Map<String, LiveObservation> values;
    Map<String, PresentWeather> weather;
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var present = executor.submit(() -> fetchPresentWeather(requested));
      DomainException rainFailure = null;
      try {
        values = KmaObservationMapper.parse(source.fetch(requested), requested);
      } catch (DomainException e) {
        values = Map.of();
        rainFailure = e;
      }
      weather = present.get();
      if (rainFailure != null && weather.isEmpty()) throw rainFailure;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new DomainException(ErrorCode.RAINFALL_UNAVAILABLE);
    } catch (ExecutionException e) {
      throw new DomainException(ErrorCode.RAINFALL_UNAVAILABLE);
    }
    var observedValues = values;
    Instant fetched = Instant.now();
    var rows =
        districts.all().stream()
            .map(
                d -> {
                  var v = observedValues.get(d.stationId());
                  var signal = RainSignalService.choose(v, weather.get(d.stationId()), fetched);
                  Long age =
                      v == null ? null : Duration.between(v.observedAt(), fetched).getSeconds();
                  String status =
                      v == null || !v.complete() ? "MISSING" : age > 300 ? "DELAYED" : "CURRENT";
                  return new LiveRainfallView.Station(
                      d.id(),
                      d.name(),
                      d.stationId(),
                      d.stationName(),
                      v == null ? null : v.observedAt(),
                      age,
                      status,
                      v == null ? null : v.fifteenMinuteMm(),
                      v == null ? null : v.sixtyMinuteMm(),
                      v == null ? null : v.dayMm(),
                      v == null ? null : v.rainDetected(),
                      v == null ? null : v.oneMinuteMm(),
                      signal.state(),
                      signal.observedAt(),
                      signal.evidence(),
                      signal.weatherCode(),
                      v == null ? null : v.temperatureC(),
                      v == null ? null : v.humidityPercent(),
                      v == null ? null : v.windSpeedMs(),
                      v == null ? null : v.pressureHpa());
                })
            .toList();
    return new LiveRainfallView(
        fetched,
        requested,
        "KMA_AWS_DIRECT",
        "https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239",
        rows);
  }

  private Map<String, PresentWeather> fetchPresentWeather(Instant requested) {
    try {
      String raw = source.fetchPresentWeather(requested);
      return raw == null ? Map.of() : KmaPresentWeatherMapper.parse(raw, requested);
    } catch (DomainException e) {
      // 보조 관측 장애로 정상 강수량까지 버리지 않는다.
      return Map.of();
    }
  }
}
