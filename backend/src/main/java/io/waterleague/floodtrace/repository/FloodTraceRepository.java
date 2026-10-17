package io.waterleague.floodtrace.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.floodtrace.entity.FloodTraceCatalog;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class FloodTraceRepository {
  public static final String VERSION = "seoul-flood-traces-20261018-v1";
  public static final String SHA256 = "fb66992c100684d2e79c249962f1a05e0b967f2b2baa25bc8a7d91b4695ea4f4";
  private final JsonService json;
  private final FloodTraceCatalog catalog;

  public FloodTraceRepository(JsonService json) {
    this.json = json;
    catalog = json.read(read("catalog.json", SHA256, 100_000), FloodTraceCatalog.class);
    if (!VERSION.equals(catalog.version()) || !"OBSERVED_EVENT_EXTENT_REFERENCE".equals(catalog.usage()))
      throw new IllegalStateException("침수흔적 카탈로그 형식 오류");
  }

  public FloodTraceCatalog catalog() { return catalog; }

  public String tile(FloodTraceCatalog.Event event, FloodTraceCatalog.Tile tile) {
    return read(event.id() + "/" + tile.id() + ".json", tile.sha256(), tile.bytes());
  }

  private String read(String relative, String expectedHash, int limit) {
    if (limit < 1 || limit > 10_000_000) throw new IllegalStateException("침수흔적 크기 오류");
    try (var stream = new ClassPathResource("floodtrace/" + VERSION + "/" + relative).getInputStream()) {
      byte[] bytes = stream.readNBytes(limit + 1);
      String raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > limit || !json.hash(raw).equals(expectedHash))
        throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
      return raw;
    } catch (IOException error) {
      throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
    }
  }
}
