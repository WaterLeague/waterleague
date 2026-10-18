package io.waterleague.infrastructure.repository;

import io.waterleague.common.service.JsonService;
import io.waterleague.infrastructure.entity.EquipmentHistory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class EquipmentHistoryRepository {
  public static final String VERSION = "equipment-history-20261018-v1";
  public static final String SHA256 =
      "5efcc339dbe4796ef27e367f39a0b14a0409923c233364cffd64a789acb4d3e6";
  private final List<EquipmentHistory> records;
  private final JsonNode source;

  public EquipmentHistoryRepository(JsonService json, InfrastructureRepository locations)
      throws IOException {
    try (var stream =
        new ClassPathResource("infrastructure/" + VERSION + ".json").getInputStream()) {
      String raw = new String(stream.readNBytes(100_001), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("시설 이력 해시 오류");
      var root = json.tree(raw);
      if (!VERSION.equals(root.path("version").asString())
          || !locations.hasUnchangedCatalog(root.path("locationCatalogSha256").asString()))
        throw new IllegalStateException("시설 이력 출처 연결 오류");
      source = root.path("source").deepCopy();
      var items = new ArrayList<EquipmentHistory>();
      var ids = new HashSet<String>();
      var locationIds = locations.records().stream().map(a -> a.id()).toList();
      for (var node : root.path("records")) {
        var item = json.read(json.write(node), EquipmentHistory.class);
        if (!ids.add(item.id()) || !locationIds.contains(item.assetId()))
          throw new IllegalStateException("시설 이력 식별자 오류");
        items.add(item);
      }
      records = List.copyOf(items);
    }
  }

  public List<EquipmentHistory> records() {
    return records;
  }

  public JsonNode source() {
    return source.deepCopy();
  }
}
