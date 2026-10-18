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
  public static final String LAYOUT_HASH =
      "fa3e4d833650df5c40d933bd0b289dd029a54e0beb73fad9b9d3ef239cb0236d";
  private final JsonNode catalog;
  private final JsonNode layout;

  public WatershedCatalogRepository(JsonService json) throws java.io.IOException {
    catalog = load(json, "watersheds/seocho-published-v1.json", HASH);
    layout = load(json, "watersheds/seocho-layout-v1.json", LAYOUT_HASH);
    if (!layout.path("sourceOriginalSha256").equals(catalog.path("sourceOriginalSha256")))
      throw new IllegalStateException("관망 표시 원본 불일치");
  }

  private JsonNode load(JsonService json, String path, String hash) throws java.io.IOException {
    try (var in = new ClassPathResource(path).getInputStream()) {
      byte[] bytes = in.readNBytes(65537);
      String raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > 65536 || !json.hash(raw).equals(hash))
        throw new IllegalStateException("공개 관망 목록 무결성 오류");
      return json.tree(raw);
    }
  }

  public JsonNode value() {
    return catalog.deepCopy();
  }

  public JsonNode layout() {
    return layout.deepCopy();
  }
}
