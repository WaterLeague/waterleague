package io.waterleague.infrastructure.repository;

import io.waterleague.common.service.JsonService;
import io.waterleague.infrastructure.entity.InfrastructureAsset;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class InfrastructureRepository {
  public static final String VERSION = "seoul-public-20261018-v1";
  public static final String SHA256 = "6b1ff662e040eca3d5da5cdc9ff5c58127bc14f0752f3ddd3ea9796debea79fb";
  private final List<InfrastructureAsset> records;
  private final List<JsonNode> sources;

  public InfrastructureRepository(JsonService json) throws IOException {
    try (var stream = new ClassPathResource("infrastructure/" + VERSION + ".json").getInputStream()) {
      String raw = new String(stream.readNBytes(2_000_000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("공개 시설 자료 해시 오류");
      var root = json.tree(raw);
      if (!VERSION.equals(root.path("version").asString()))
        throw new IllegalStateException("공개 시설 자료 버전 오류");
      var assets = new ArrayList<InfrastructureAsset>();
      var provenance = new ArrayList<JsonNode>();
      for (var source : root.path("sources")) provenance.add(source.deepCopy());
      for (var asset : root.path("assets"))
        assets.add(json.read(json.write(asset), InfrastructureAsset.class));
      records = List.copyOf(assets);
      sources = List.copyOf(provenance);
    }
  }

  public List<InfrastructureAsset> records() { return records; }
  public List<JsonNode> sources() { return sources.stream().map(JsonNode::deepCopy).toList(); }
}
