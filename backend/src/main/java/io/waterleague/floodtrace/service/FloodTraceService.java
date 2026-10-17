package io.waterleague.floodtrace.service;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.floodtrace.repository.FloodTraceRepository;
import io.waterleague.floodtrace.view.FloodTraceView;
import org.springframework.stereotype.Service;

@Service
public class FloodTraceService {
  private final FloodTraceRepository repository;
  public FloodTraceService(FloodTraceRepository repository) { this.repository = repository; }

  public FloodTraceView catalog() {
    return new FloodTraceView(FloodTraceRepository.SHA256, repository.catalog());
  }

  public TileResponse tile(String eventId, String tileId) {
    // 요청 문자열로 파일 경로를 조합하지 않고 고정 목록의 항목만 사용한다.
    var event = repository.catalog().events().stream().filter(e -> e.id().equals(eventId))
        .findFirst().orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    var tile = event.tiles().stream().filter(t -> t.id().equals(tileId))
        .findFirst().orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    return new TileResponse(tile.sha256(), repository.tile(event, tile));
  }

  public record TileResponse(String sha256, String json) {}
}
