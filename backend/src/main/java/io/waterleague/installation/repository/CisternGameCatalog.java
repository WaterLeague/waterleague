package io.waterleague.installation.repository;

import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

@Repository
public class CisternGameCatalog {
  public static final String SHA256 =
      "20da4bc15546b77aa680d07d61bc1d95a0f0c7aae95667d6c46fa080c2c270f3";
  public static final String TYPE = "RAINWATER_CISTERN";
  private final JsonNode rules;
  private final JsonService json;

  public CisternGameCatalog(JsonService json) {
    this.json = json;
    try (var stream = new ClassPathResource("facilities/cistern-game-v1.json").getInputStream()) {
      var raw = new String(stream.readNBytes(65536), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new IllegalStateException("이용조 설계 해시 오류");
      rules = json.tree(raw);
    } catch (IOException e) {
      throw new IllegalStateException("이용조 설계 읽기 실패", e);
    }
  }

  public JsonNode metadata(JsonNode source) {
    ObjectNode value = (ObjectNode) source.deepCopy();
    value.set("facilityDesignSet", rules.path("facilityDesignSet").deepCopy());
    ((ObjectNode) value.path("unitCosts")).set(TYPE, rules.path("cost").path("unitCost").deepCopy());
    ((ObjectNode) value.path("costModel").path("facilities")).set(TYPE, rules.path("cost").deepCopy());
    value.put("costSourceSha256", json.hash(source.path("costSourceSha256").asString() + ":" + SHA256));
    value.put("cisternGameSha256", SHA256);
    rules.path("limitations").forEach(item -> ((ArrayNode) value.path("limitations")).add(item));
    return value;
  }

  public JsonNode cell(JsonNode source) {
    if (!source.path("kind").asString().equals("ROOF")) return source;
    boolean roof = false, cistern = false;
    for (var type : source.path("allowedTypes")) {
      roof |= type.asString().equals("GREEN_ROOF");
      cistern |= type.asString().equals(TYPE);
    }
    if (!roof || cistern) return source;
    ObjectNode value = (ObjectNode) source.deepCopy();
    ((ArrayNode) value.path("allowedTypes")).add(TYPE);
    return value;
  }
}
