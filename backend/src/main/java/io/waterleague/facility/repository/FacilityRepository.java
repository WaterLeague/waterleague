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
  private final JsonNode latest;
  private final JsonNode v3;
  private final JsonNode v5;
  public static final String V5_SHA256 = "0b37b1779f60533bb344158eef8a6ec1510d60a533ec99d81c3e98324b02c62e";
  private final JsonNode pavementMaintenance;
  public static final String PAVEMENT_MAINTENANCE_SHA256 =
      "a9166ec93e6a6af4c460028f438c33fc67af0a1675502491e04f248c8e7dfd88";
  public static final String V3_SHA256 =
      "2a703170835529fe4d9b2c729157a04b7555faf9a1097f481be4269bfe279d5c";
  public static final String LATEST_SHA256 =
      "8af82e01704cf1495f185d9a0a410898e6007a468274c905e75b939f9abde133";

  public FacilityRepository(JsonService json) throws IOException {
    catalog = load(json, 2, SHA256);
    latest = load(json, 4, LATEST_SHA256);
    v5 = load(json, 5, V5_SHA256);
    v3 = load(json, 3, V3_SHA256);
    legacy = load(json, 1, LEGACY_SHA256);
    pavementMaintenance =
        loadPath(json, "facilities/pavement-maintenance-v1.json", PAVEMENT_MAINTENANCE_SHA256);
  }

  private JsonNode load(JsonService json, int version, String hash) throws IOException {
    return loadPath(json, "facilities/epa-designs-v" + version + ".json", hash);
  }

  private JsonNode loadPath(JsonService json, String path, String hash) throws IOException {
    try (var stream = new ClassPathResource(path).getInputStream()) {
      var raw = new String(stream.readNBytes(100000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(hash)) throw new IllegalStateException("시설 제원 해시 오류");
      return json.tree(raw);
    }
  }

  public JsonNode pavementMaintenance() {
    return pavementMaintenance.deepCopy();
  }

  public JsonNode v3() {
    return v3.deepCopy();
  }

  public JsonNode v5() { return v5.deepCopy(); }

  public JsonNode latest() {
    return latest.deepCopy();
  }

  public JsonNode catalog(boolean previous) {
    return (previous ? legacy : catalog).deepCopy();
  }
}
