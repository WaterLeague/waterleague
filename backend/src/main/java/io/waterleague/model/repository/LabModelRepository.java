package io.waterleague.model.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.entity.LabModel;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class LabModelRepository {
  private final Map<String, LabModel> models;
  private final String defaultHash;

  public LabModelRepository(JsonService json) throws java.io.IOException {
    String catalogSource = read("current/catalog.json");
    if (!json.hash(catalogSource)
        .equals("0835043218ada24eb9a58f6fb0ac9b7382d8394499f8176fbe289896ab4d506b"))
      throw new IllegalStateException("현재 연구 모델 목록 해시 오류");
    var catalog = json.tree(catalogSource);
    if (catalog.path("schemaVersion").asInt() != 1
        || !catalog.path("models").isArray()
        || catalog.path("models").size() < 1
        || catalog.path("models").size() > 256) throw new IllegalStateException("모델 카탈로그 형식 오류");
    Map<String, LabModel> entries = new LinkedHashMap<>();
    Set<String> ids = new HashSet<>(), files = new HashSet<>();
    for (var entry : catalog.path("models")) {
      String name = entry.path("file").asString(), hash = entry.path("sha256").asString();
      String id = entry.path("id").asString();
      if (!name.matches("[a-z0-9][a-z0-9-]{0,100}\\.json")
          || name.equals("catalog.json")
          || !hash.matches("[a-f0-9]{64}")
          || entries.containsKey(hash)
          || !ids.add(id)
          || !files.add(name)) throw new IllegalStateException("모델 식별자 오류");
      String source = read("current/" + name);
      var model = json.tree(source);
      if (!json.hash(source).equals(hash)
          || !model.path("mapId").asString().equals("seongsu-ngii-2025-v2")
          || !id.equals(model.path("id").asString())
          || !model.path("simulationAvailable").asBoolean()
          || model.path("officialEvaluationAvailable").asBoolean()
          || !model.path("validationLevel").asString().equals("EXPLORATORY"))
        throw new IllegalStateException("모델 등록 계약 불일치");
      entries.put(hash, new LabModel(hash, source, model));
    }
    defaultHash = catalog.path("defaultModelHash").asString();
    if (!entries.containsKey(defaultHash)) throw new IllegalStateException("기본 모델 누락");
    models = Collections.unmodifiableMap(entries);
  }

  private static String read(String name) throws java.io.IOException {
    try (var stream = new ClassPathResource("models/" + name).getInputStream()) {
      byte[] bytes = stream.readNBytes(2 * 1024 * 1024 + 1);
      if (bytes.length > 2 * 1024 * 1024) throw new IllegalStateException("모델 크기 초과");
      return new String(bytes, StandardCharsets.UTF_8);
    }
  }

  public LabModel require(String hash) {
    var item = models.get(hash == null ? defaultHash : hash);
    if (item == null) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return item;
  }

  public boolean contains(String hash) {
    return models.containsKey(hash);
  }

  public List<LabModel> all() {
    return List.copyOf(models.values());
  }

  public String source() {
    return require(defaultHash).source();
  }

  public String hash() {
    return defaultHash;
  }

  public JsonNode model() {
    return require(defaultHash).model();
  }
}
