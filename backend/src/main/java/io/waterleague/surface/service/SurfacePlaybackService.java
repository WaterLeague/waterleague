package io.waterleague.surface.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.sharedresearch.service.SharedResearchService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.repository.SurfacePlaybackRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class SurfacePlaybackService {
  public enum Access {
    HISTORICAL_OWNER,
    SHARED_OWNER,
    CONSENTED_ORGANIZATION,
    LATEST_INSTALLATION
  }

  private final HistoricalService historical;
  private final SharedResearchService shared;
  private final SurfacePlaybackRepository results;
  private final JsonService json;
  private final io.waterleague.installation.repository.InstallationRepository installations;
  private final io.waterleague.physics.repository.PhysicsRepository physics;

  public SurfacePlaybackService(
      HistoricalService historical,
      SharedResearchService shared,
      SurfacePlaybackRepository results,
      JsonService json,
      io.waterleague.installation.repository.InstallationRepository installations,
      io.waterleague.physics.repository.PhysicsRepository physics) {
    this.historical = historical;
    this.shared = shared;
    this.results = results;
    this.json = json;
    this.installations = installations;
    this.physics = physics;
  }

  private SurfacePublication authorize(UUID actor, Access access, UUID id) {
    if (access == Access.LATEST_INSTALLATION) {
      installations
          .find(id)
          .filter(i -> i.ownerId().equals(actor))
          .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
      var job =
          physics
              .completed(id)
              .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
      return authorize(actor, Access.SHARED_OWNER, job.id());
    }
    String result;
    UUID token;
    SurfacePublication.Scope scope;
    if (access == Access.HISTORICAL_OWNER) {
      var job = historical.require(actor, id);
      if (!job.state().equals("SUCCEEDED")) throw new DomainException(ErrorCode.CONFLICT);
      result = job.result();
      token = job.leaseToken();
      scope = SurfacePublication.Scope.HISTORICAL;
    } else {
      var job = shared.surfaceAccess(actor, access == Access.CONSENTED_ORGANIZATION, id);
      result = job.result();
      token = job.leaseToken();
      scope = SurfacePublication.Scope.SHARED;
    }
    if (result == null || token == null) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    var publication = json.tree(result).path("surfacePlayback");
    if (!publication.isObject()
        || publication.path("schemaVersion").asInt() != 1
        || !publication.path("catalogSha256").asString().matches("[a-f0-9]{64}")
        || !publication.path("surfaceResultSha256").asString().matches("[a-f0-9]{64}"))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return new SurfacePublication(
        scope,
        id,
        token,
        publication.path("catalogSha256").asString(),
        publication.path("surfaceResultSha256").asString());
  }

  public Object read(UUID actor, Access access, UUID id, SurfaceFrameRequest request) {
    var publication = authorize(actor, access, id);
    var result =
        request == null ? results.catalogView(publication) : results.frame(publication, request);
    // 파일 조회 중 동의·작업 결과가 바뀐 경우 이전 결과도 반환하지 않는다.
    if (!publication.equals(authorize(actor, access, id)))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return result;
  }
}
