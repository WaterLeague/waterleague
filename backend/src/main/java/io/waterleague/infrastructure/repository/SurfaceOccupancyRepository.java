package io.waterleague.infrastructure.repository;

import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SurfaceOccupancyRepository {
  public static final String VERSION = "seoul-basin-footprints-20261018-v4";
  public static final String SHA256 =
      "5b15ba1ff3df4460f33a4bac3dd68485c082d7c56d75eec8653d8631444eb871";
  private final Map<String, List<JsonNode>> exclusions = new HashMap<>();
  private final JsonService json;
  private final JsonNode evidence;

  public SurfaceOccupancyRepository(JsonService json) throws IOException {
    this.json = json;
    try (var stream =
        new ClassPathResource("infrastructure/" + VERSION + ".json").getInputStream()) {
      String raw = new String(stream.readNBytes(1_000_001), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("공개 저류 영역 해시 오류");
      var root = json.tree(raw);
      for (var row : root.path("exclusions"))
        exclusions
            .computeIfAbsent(
                row.path("districtId").asString() + ":" + row.path("cellId").asString(),
                ignored -> new ArrayList<>())
            .add(row.deepCopy());
      evidence =
          json.tree(
              json.write(
                  Map.of(
                      "version",
                      VERSION,
                      "sha256",
                      SHA256,
                      "sourceSha256",
                      root.path("sourceSha256").asString(),
                      "scope",
                      root.path("scope").asString(),
                      "historicalExistenceVerified",
                      false)));
    }
  }

  public JsonNode evidence() {
    return evidence.deepCopy();
  }

  public JsonNode exclusion(String district, String cell, String modelHash, String kind) {
    var rows = exclusions.get(district + ":" + cell);
    if (rows == null) return null;
    // 다른 후보 버전에 같은 식별자를 재사용해도 이전 교차 판정을 전용하지 않는다.
    if (!kind.equals("GROUND")
        || rows.stream().anyMatch(r -> !modelHash.equals(r.path("siteModelHash").asString())))
      throw new IllegalStateException("공개 저류 영역 후보 결속 오류");
    return json.tree(json.write(Map.of("policy", evidence(), "assets", rows)));
  }
}
