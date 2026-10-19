package io.waterleague.urban.service;

import io.waterleague.common.exception.*;
import io.waterleague.urban.entity.UrbanArea;
import io.waterleague.urban.mapper.UrbanLiveMapper;
import io.waterleague.urban.repository.*;
import io.waterleague.urban.view.UrbanLiveView;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.stereotype.Service;

@Service
public class UrbanLiveService {
  private final UrbanAreaRepository areas;
  private final SeoulUrbanRepository source;
  private final UrbanLiveMapper mapper;
  private final Clock clock;
  private final ConcurrentHashMap<String, Cached> cache = new ConcurrentHashMap<>();
  private final ConcurrentHashMap<String, CompletableFuture<UrbanLiveView.Place>> pending =
      new ConcurrentHashMap<>();
  private final Semaphore connections = new Semaphore(4);

  private record Cached(Instant until, UrbanLiveView.Place value) {}

  @org.springframework.beans.factory.annotation.Autowired
  public UrbanLiveService(
      UrbanAreaRepository areas, SeoulUrbanRepository source, UrbanLiveMapper mapper) {
    this(areas, source, mapper, Clock.systemUTC());
  }

  public UrbanLiveService(
      UrbanAreaRepository areas, SeoulUrbanRepository source, UrbanLiveMapper mapper, Clock clock) {
    this.areas = areas;
    this.source = source;
    this.mapper = mapper;
    this.clock = clock;
  }

  public UrbanLiveView latest(List<String> ids) {
    if (ids.isEmpty() || ids.size() > 6 || new HashSet<>(ids).size() != ids.size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var selected = ids.stream().map(areas::require).toList();
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var jobs = selected.stream().map(a -> executor.submit(() -> latest(a))).toList();
      var values = new ArrayList<UrbanLiveView.Place>();
      for (var job : jobs) values.add(job.get());
      return new UrbanLiveView(
          UrbanAreaRepository.HASH, SeoulUrbanRepository.SOURCE, List.copyOf(values));
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    }
  }

  private UrbanLiveView.Place latest(UrbanArea area) {
    var previous = cache.get(area.id());
    if (previous != null && clock.instant().isBefore(previous.until)) return previous.value;
    var mine = new CompletableFuture<UrbanLiveView.Place>();
    var active = pending.putIfAbsent(area.id(), mine);
    if (active != null) return active.join();
    try {
      var value = fetch(area);
      long seconds = value.population() == null || value.traffic() == null ? 60 : 300;
      Instant until = clock.instant().plusSeconds(seconds);
      if (value.population() != null && value.population().validUntil().isBefore(until))
        until = value.population().validUntil();
      if (value.traffic() != null && value.traffic().validUntil().isBefore(until))
        until = value.traffic().validUntil();
      cache.put(area.id(), new Cached(until, value));
      mine.complete(value);
      return value;
    } catch (RuntimeException e) {
      mine.completeExceptionally(e);
      throw e;
    } finally {
      pending.remove(area.id(), mine);
    }
  }

  private UrbanLiveView.Place fetch(UrbanArea area) {
    try {
      if (!connections.tryAcquire(5, TimeUnit.SECONDS))
        return new UrbanLiveView.Place(area.id(), area.name(), null, null, "BUSY", "BUSY");
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    }
    try {
      UrbanLiveView.Population population = null;
      UrbanLiveView.Traffic traffic = null;
      String pStatus = "CURRENT_WEB_ESTIMATE", tStatus = "CURRENT_AREA_AVERAGE";
      try {
        population =
            mapper.population(source.population(area.name()), area.name(), clock.instant());
      } catch (DomainException e) {
        pStatus = e.code().name();
      }
      try {
        traffic = mapper.traffic(source.traffic(area.name()), area.name(), clock.instant());
      } catch (DomainException e) {
        tStatus = e.code().name();
      }
      return new UrbanLiveView.Place(area.id(), area.name(), population, traffic, pStatus, tStatus);
    } finally {
      connections.release();
    }
  }
}
