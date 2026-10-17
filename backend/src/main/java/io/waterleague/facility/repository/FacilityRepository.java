package io.waterleague.facility.repository;

import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class FacilityRepository {
  public static final String SHA256 =
      "115d89e1935be403989a08c81111a06d081ccbc422729ace2b57cd75a46cebb9";
  private final JsonNode catalog;

  public FacilityRepository(JsonService json) throws IOException {
    try (var stream = new ClassPathResource("facilities/epa-designs-v1.json").getInputStream()) {
      var raw = new String(stream.readNBytes(100000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("시설 제원 해시 오류");
      catalog = json.tree(raw);
    }
  }

  public JsonNode catalog() {
    return catalog.deepCopy();
  }
}
