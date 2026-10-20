package io.waterleague.infrastructure.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SurfaceOccupancyRepository {
  public static final String VERSION = "seoul-native-infrastructure-20261020-v1";
  public static final String SHA256 =
      "386b77e33b647a879527251c7dceb091ab4507479ee77b189b35f8cd3da7b44f";
  private final Map<String, List<JsonNode>> references;
  private final JsonService json;
  private final JsonNode evidence;

  public SurfaceOccupancyRepository(JsonService json) {
    this.json = json;
    try (var input =
        new ClassPathResource("infrastructure/native-v1/associations.json").getInputStream()) {
      String raw = new String(input.readNBytes(2_000_001), StandardCharsets.UTF_8);
      var root = json.tree(raw);
      if (!json.hash(raw).equals(SHA256)
          || !root.path("version").asString().equals(VERSION)
          || !root.path("sourceSha256")
              .asString()
              .equals("d0ef74f9cf919a18f766f27b540c72119fc1d4f2583fc1525d4c289791f1fa94")
          || !root.path("siteCatalogSha256")
              .asString()
              .equals("4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7")
          || !root.path("exclusions").isArray()
          || !root.path("exclusions").isEmpty()) invalid();
      var values = new HashMap<String, List<JsonNode>>();
      for (var row : root.path("associations")) {
        if (row.path("footprintVerified").asBoolean()
            || !row.path("verticalLayer").asString().equals("UNKNOWN")
            || !row.path("siteModelHash").equals(root.path("siteCatalogSha256"))) invalid();
        values
            .computeIfAbsent(
                row.path("districtId").asString() + ":" + row.path("cellId").asString(),
                ignored -> new ArrayList<>())
            .add(row.deepCopy());
      }
      var frozen = new HashMap<String, List<JsonNode>>();
      values.forEach((key, value) -> frozen.put(key, List.copyOf(value)));
      references = Map.copyOf(frozen);
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
                      "siteCatalogSha256",
                      root.path("siteCatalogSha256").asString(),
                      "scope",
                      root.path("scope").asString(),
                      "historicalExistenceVerified",
                      false,
                      "confirmedFootprintCount",
                      0)));
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  public JsonNode evidence() {
    return evidence.deepCopy();
  }

  public JsonNode forCandidate(String district, String cell) {
    var rows = references.get(district + ":" + cell);
    return rows == null
        ? null
        : json.tree(json.write(Map.of("policy", evidence(), "references", rows)));
  }

  private static void invalid() {
    throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
  }
}
