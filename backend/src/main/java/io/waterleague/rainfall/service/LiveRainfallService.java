package io.waterleague.rainfall.service;

import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.rainfall.mapper.KmaObservationMapper;
import io.waterleague.rainfall.repository.KmaLiveRepository;
import io.waterleague.rainfall.view.LiveRainfallView;
import java.time.*;
import java.time.temporal.ChronoUnit;
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
    // 생산 중인 현재 분의 결측을 피하되 응답의 실제 관측 시각과 지연을 그대로 공개한다.
    Instant requested = Instant.now().truncatedTo(ChronoUnit.MINUTES).minusSeconds(120);
    var values = KmaObservationMapper.parse(source.fetch(requested), requested);
    Instant fetched = Instant.now();
    var rows =
        districts.all().stream()
            .map(
                d -> {
                  var v = values.get(d.stationId());
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
                      v == null ? "UNKNOWN" : v.rainState());
                })
            .toList();
    return new LiveRainfallView(
        fetched,
        requested,
        "KMA_AWS_DIRECT",
        "https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239",
        rows);
  }
}
