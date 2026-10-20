package io.waterleague.infrastructure.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.infrastructure.entity.InfrastructureAsset;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class InfrastructureRepository {
  public static final String VERSION = "seoul-native-infrastructure-20261020-v1";
  public static final String SHA256 =
      "d0ef74f9cf919a18f766f27b540c72119fc1d4f2583fc1525d4c289791f1fa94";
  private static final String HISTORY_LOCATION_SHA256 =
      "6b1ff662e040eca3d5da5cdc9ff5c58127bc14f0752f3ddd3ea9796debea79fb";
  private final List<InfrastructureAsset> records;
  private final List<JsonNode> sources;

  public InfrastructureRepository(JsonService json) {
    try (var input =
        new ClassPathResource("infrastructure/native-v1/catalog.json").getInputStream()) {
      String raw = new String(input.readNBytes(2_000_001), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) invalid();
      var root = json.tree(raw);
      if (!VERSION.equals(root.path("version").asString())) invalid();
      var items = new ArrayList<InfrastructureAsset>();
      var provenance = new ArrayList<JsonNode>();
      var sourceIds = new HashSet<String>();
      for (var source : root.path("sources")) {
        if (!sourceIds.add(source.path("id").asString())
            || !source.path("license").asString().equals("KOGL_TYPE_1")) invalid();
        provenance.add(source.deepCopy());
      }
      var ids = new HashSet<String>();
      for (var node : root.path("assets")) {
        var asset = json.read(json.write(node), InfrastructureAsset.class);
        if (!ids.add(asset.id())
            || !sourceIds.contains(asset.sourceId())
            || asset.footprint() != null && !asset.footprint().isNull()
            || !asset.geometryEvidence().equals("LOCATION_POINT")
            || !asset.verticalLayer().equals("UNKNOWN")) invalid();
        items.add(asset);
      }
      records = List.copyOf(items);
      sources = List.copyOf(provenance);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  public List<InfrastructureAsset> records() {
    return records;
  }

  public List<JsonNode> sources() {
    return sources.stream().map(JsonNode::deepCopy).toList();
  }

  public boolean hasArchivedLocationSource(String hash) {
    // 설비 이력의 원 위치점 목록은 보존하되 현재 지도 형상으로 조회하지 않는다.
    return HISTORY_LOCATION_SHA256.equals(hash);
  }

  private static void invalid() {
    throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
  }
}
