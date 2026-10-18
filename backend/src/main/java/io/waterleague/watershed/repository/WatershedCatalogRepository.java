package io.waterleague.watershed.repository;

import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class WatershedCatalogRepository {
  public static final String HASH =
      "beaddba8868b6f1f6bbf35b1d53d4695a94db99498d8988f90d62013cf8f053c";
  private final JsonNode catalog;

  public WatershedCatalogRepository(JsonService json) throws java.io.IOException {
    try (var in = new ClassPathResource("watersheds/seocho-published-v1.json").getInputStream()) {
      byte[] bytes = in.readNBytes(65537);
      String raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > 65536 || !json.hash(raw).equals(HASH))
        throw new IllegalStateException("공개 관망 목록 무결성 오류");
      catalog = json.tree(raw);
    }
  }

  public JsonNode value() {
    return catalog.deepCopy();
  }
}
