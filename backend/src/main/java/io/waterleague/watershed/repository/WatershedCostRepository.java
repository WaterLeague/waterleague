package io.waterleague.watershed.repository;

import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class WatershedCostRepository {
  public static final String HASH =
      "9a182d390c74c8adad4f14eb6d575e1a556057fb69b87e5b802ca131dcfc5739";
  private final JsonNode catalog;

  public WatershedCostRepository(JsonService json) throws java.io.IOException {
    try (var in = new ClassPathResource("watersheds/connected-costs-v1.json").getInputStream()) {
      byte[] bytes = in.readNBytes(65537);
      String raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > 65536 || !json.hash(raw).equals(HASH))
        throw new IllegalStateException("관망 시설 참고 원가 무결성 오류");
      catalog = json.tree(raw);
    }
  }

  public JsonNode value() {
    return catalog.deepCopy();
  }
}
