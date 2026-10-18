package io.waterleague.surface.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.exception.SurfaceResultException;
import io.waterleague.surface.repository.PublicSurfaceModelRepository;
import io.waterleague.surface.repository.SurfacePlaybackRepository;
import io.waterleague.surface.view.PublicSurfaceView;
import io.waterleague.surface.view.SurfaceView;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PublicSurfaceService {
  private record Publication(
      SurfacePublication reference,
      PublicSurfaceModelRepository.Model model,
      Instant lastFrameAt,
      SurfaceView.Catalog catalog) {}

  private final Path index;
  private final JsonService json;
  private final PublicSurfaceModelRepository models;
  private final SurfacePlaybackRepository results;

  public PublicSurfaceService(
      @Value("${waterleague.artifacts}") String root,
      JsonService json,
      PublicSurfaceModelRepository models,
      SurfacePlaybackRepository results) {
    this.index = Path.of(root).toAbsolutePath().normalize().resolve("public-surface/current.json");
    this.json = json;
    this.models = models;
    this.results = results;
  }

  private void require(boolean condition) {
    if (!condition) throw new SurfaceResultException();
  }

  private static boolean recent(Instant at, Instant now) {
    return !at.isAfter(now) && !at.isBefore(now.minusSeconds(300));
  }

  private List<Publication> active(Instant now) {
    if (!Files.exists(index, LinkOption.NOFOLLOW_LINKS)) return List.of();
    try {
      require(
          Files.isRegularFile(index, LinkOption.NOFOLLOW_LINKS)
              && index.toRealPath().equals(index)
              && Files.size(index) <= 256000);
      byte[] raw;
      try (var in = Files.newInputStream(index, LinkOption.NOFOLLOW_LINKS)) {
        raw = in.readNBytes(256001);
      }
      require(raw.length <= 256000);
      var data = json.tree(new String(raw, StandardCharsets.UTF_8));
      require(
          data.path("schemaVersion").asInt() == 1
              && data.path("runs").isArray()
              && data.path("runs").size() <= 128);
      var values = new ArrayList<Publication>();
      var basins = new HashSet<String>();
      var ids = new HashSet<UUID>();
      for (var row : data.path("runs")) {
        var approved = models.find(row.path("basinId").asString());
        // 공개 게시 전용 모형만 허용하며 개인 실행의 동의·소유 권한을 이 경로로 우회하지 않는다.
        if (approved.isEmpty()) continue;
        var model = approved.get();
        require(
            row.path("scenario").asString().equals("PUBLIC_BASELINE")
                && row.path("numericalStatus").asString().equals("PASSED")
                && row.path("forcingSource").asString().equals("OFFICIAL_OBSERVATIONS")
                && row.path("inputBundleSha256").asString().equals(model.inputBundleSha256())
                && row.path("numericalPolicySha256")
                    .asString()
                    .equals(model.numericalPolicySha256()));
        Instant at = Instant.parse(row.path("lastFrameAt").asString());
        if (!recent(at, now)) continue;
        UUID id = UUID.fromString(row.path("id").asString()),
            token = UUID.fromString(row.path("token").asString());
        require(ids.add(id) && basins.add(model.id()));
        var reference =
            new SurfacePublication(
                SurfacePublication.Scope.PUBLIC_CURRENT,
                id,
                token,
                row.path("catalogSha256").asString(),
                row.path("surfaceResultSha256").asString());
        var catalog = results.catalogView(reference);
        Instant start = Instant.parse(catalog.startUtc());
        double last = catalog.timesSeconds().getLast();
        require(
            catalog.classification().equals(model.classification())
                && catalog.originProjected()[0] == 198128.
                && catalog.originProjected()[1] == 551989.
                && start.plusNanos(Math.round(last * 1e9)).equals(at));
        values.add(new Publication(reference, model, at, catalog));
      }
      return List.copyOf(values);
    } catch (SurfaceResultException error) {
      throw error;
    } catch (Exception error) {
      throw new SurfaceResultException();
    }
  }

  public PublicSurfaceView.Current current(SurfaceFrameRequest area, Instant now) {
    area.validate();
    var views = new ArrayList<PublicSurfaceView.Run>();
    for (var p : active(now)) {
      var bounds = p.model().bounds();
      if (bounds[2] < area.minX()
          || bounds[0] > area.maxX()
          || bounds[3] < area.minY()
          || bounds[1] > area.maxY()) continue;
      views.add(
          new PublicSurfaceView.Run(
              p.reference().jobId(),
              p.model().id(),
              p.model().name(),
              p.model().inputBundleSha256(),
              p.model().numericalPolicySha256(),
              p.lastFrameAt(),
              p.catalog()));
    }
    return new PublicSurfaceView.Current(now, List.copyOf(views));
  }

  public SurfaceView.Frame frame(UUID id, SurfaceFrameRequest request, Instant now) {
    request.validate();
    long readStarted = System.nanoTime();
    var p =
        active(now).stream()
            .filter(v -> v.reference().jobId().equals(id))
            .findFirst()
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    var frame = results.frame(p.reference(), request);
    var at = Instant.parse(p.catalog().startUtc()).plusNanos(Math.round(frame.timeSeconds() * 1e9));
    Instant completedAt = now.plusNanos(System.nanoTime() - readStarted);
    if (!recent(at, completedAt)) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    if (active(completedAt).stream().noneMatch(v -> v.reference().equals(p.reference())))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return frame;
  }
}
