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
  public static final String VERSION = "seoul-public-20261019-v3";
  public static final String V2_SHA256 =
      "325bb73079cd70017a57a0d346e93c6f0a8376af181542dfa461fa746aa21764";
  public static final String SHA256 =
      "44af12ac60cc058bc867b5b82f11afcfe53cf6da7afef37f85660f96cb10854a";
  private static final String PREVIOUS_SHA256 =
      "6b1ff662e040eca3d5da5cdc9ff5c58127bc14f0752f3ddd3ea9796debea79fb";
  private final List<InfrastructureAsset> records;
  private final List<JsonNode> sources;
  private final Set<String> previousAssetIds = new HashSet<>();
  private final Set<String> previousSourceIds = new HashSet<>();

  public InfrastructureRepository(JsonService json) throws IOException {
    try (var stream =
        new ClassPathResource("infrastructure/" + VERSION + ".json").getInputStream()) {
      String raw = new String(stream.readNBytes(2_000_000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("공개 시설 자료 해시 오류");
      var root = json.tree(raw);
      if (!VERSION.equals(root.path("version").asString()))
        throw new IllegalStateException("공개 시설 자료 버전 오류");
      // 이력이 참조하는 이전 카탈로그의 모든 기록·출처가 변경 없이 포함됐는지 확인한다.
      try (var prior =
          new ClassPathResource("infrastructure/seoul-public-20261018-v2.json").getInputStream()) {
        String oldRaw = new String(prior.readNBytes(2_000_000), StandardCharsets.UTF_8);
        if (!json.hash(oldRaw).equals(V2_SHA256)) throw new IllegalStateException("이전 시설 자료 해시 오류");
        var old = json.tree(oldRaw);
        for (String field : List.of("assets", "sources")) {
          var current = new HashMap<String, JsonNode>();
          for (var node : root.path(field)) current.put(node.path("id").asString(), node);
          for (var node : old.path(field)) {
            (field.equals("assets") ? previousAssetIds : previousSourceIds)
                .add(node.path("id").asString());
            if (!node.equals(current.get(node.path("id").asString())))
              throw new IllegalStateException("이전 시설 기록 변경");
          }
        }
      }
      var assets = new ArrayList<InfrastructureAsset>();
      var provenance = new ArrayList<JsonNode>();
      for (var source : root.path("sources")) provenance.add(source.deepCopy());
      for (var asset : root.path("assets"))
        assets.add(json.read(json.write(asset), InfrastructureAsset.class));
      records = List.copyOf(assets);
      sources = List.copyOf(provenance);
    }
  }

  public List<InfrastructureAsset> records(boolean previous) {
    if (previous) return records.stream().filter(a -> previousAssetIds.contains(a.id())).toList();
    return records;
  }

  public List<InfrastructureAsset> records() {
    return records(false);
  }

  public boolean hasUnchangedCatalog(String hash) {
    return SHA256.equals(hash) || V2_SHA256.equals(hash) || PREVIOUS_SHA256.equals(hash);
  }

  public List<JsonNode> sources(boolean previous) {
    return sources.stream()
        .filter(s -> !previous || previousSourceIds.contains(s.path("id").asString()))
        .map(JsonNode::deepCopy)
        .toList();
  }
}
