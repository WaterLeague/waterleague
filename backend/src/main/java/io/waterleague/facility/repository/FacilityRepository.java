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
      "068094e1fb8214c60a86bcbc64e039964ba771beb90400702d34f6b741e2d987";
  public static final String LEGACY_SHA256 =
      "115d89e1935be403989a08c81111a06d081ccbc422729ace2b57cd75a46cebb9";
  private final JsonNode catalog;
  private final JsonNode legacy;

  public FacilityRepository(JsonService json) throws IOException {
    catalog = load(json, 2, SHA256);
    legacy = load(json, 1, LEGACY_SHA256);
  }

  private JsonNode load(JsonService json, int version, String hash) throws IOException {
    try (var stream =
        new ClassPathResource("facilities/epa-designs-v" + version + ".json").getInputStream()) {
      var raw = new String(stream.readNBytes(100000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(hash)) throw new IllegalStateException("시설 제원 해시 오류");
      return json.tree(raw);
    }
  }

  public JsonNode catalog(boolean previous) {
    return (previous ? legacy : catalog).deepCopy();
  }
}
