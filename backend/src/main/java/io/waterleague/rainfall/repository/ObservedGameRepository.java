package io.waterleague.rainfall.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.rainfall.entity.ObservedForcing;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class ObservedGameRepository {
  public static final String SHA256 =
      "f08b92fa00db08126e86b379583299a831764b958a4f131de4647ebde95e6fdb";
  private final JsonNode catalog;
  private final Map<String, ObservedForcing> models;
  private final JsonNode events;

  public ObservedGameRepository(JsonService json) {
    try {
      String raw = read("catalog.json", 512 * 1024);
      if (!json.hash(raw).equals(SHA256)) invalid();
      catalog = json.tree(raw);
      if (!catalog.path("id").asString().equals("SEOUL_NGII_GAME_V2")
          || catalog.path("schemaVersion").asInt() != 1
          || !catalog.path("coordinateSystem").asString().equals("EPSG:5186")
          || !catalog.path("siteCatalogSha256").asString().equals(
              "4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7")
          || catalog.path("regions").size() != 25 || catalog.path("models").size() != 100) invalid();
      var values = new LinkedHashMap<String, ObservedForcing>();
      for (var entry : catalog.path("models")) {
        String id = entry.path("id").asString(), file = entry.path("file").asString(), hash = entry.path("sha256").asString();
        if (!id.matches("ngii-11[0-9]{3}-(default|seoul-[0-9]{8})-[0-9]{1,5}")
            || !file.equals("models/" + id + ".json") || !hash.matches("[a-f0-9]{64}")) invalid();
        String body = read(file, 256 * 1024);
        var model = json.tree(body);
        if (!json.hash(body).equals(hash)
            || body.getBytes(StandardCharsets.UTF_8).length != entry.path("bytes").asInt()
            || !model.path("kind").asString().equals("OBSERVED_FORCING_BINDING")
            || !model.path("id").asString().equals(id)
            || !model.path("districtId").equals(entry.path("districtId"))
            || !model.path("siteCatalogSha256").equals(catalog.path("siteCatalogSha256"))
            || values.put(hash, new ObservedForcing(hash, body, model)) != null) invalid();
      }
      models = Map.copyOf(values);
      var districtIds = new HashSet<String>();
      var references = new HashSet<String>();
      for (var region : catalog.path("regions")) {
        String district = region.path("districtId").asString();
        if (!district.matches("11[0-9]{3}") || !districtIds.add(district)
            || region.path("modelHashes").size() != 4 || region.path("eventModelHashes").size() != 3
            || !region.path("siteCatalogSha256").equals(catalog.path("siteCatalogSha256"))) invalid();
        boolean hasDefault = false;
        for (var hash : region.path("modelHashes")) {
          var forcing = values.get(hash.asString());
          if (forcing == null || !references.add(hash.asString())
              || !forcing.model().path("districtId").asString().equals(district)
              || !forcing.model().path("mapId").asString().equals("seoul-ngii-v1-" + district)) invalid();
          hasDefault |= hash.equals(region.path("defaultModelHash"));
        }
        if (!hasDefault) invalid();
      }
      if (references.size() != values.size()) invalid();
      String eventSource = read("events.json", 1024 * 1024);
      if (!catalog.path("events").path("file").asString().equals("events.json")
          || !json.hash(eventSource).equals(catalog.path("events").path("sha256").asString())) invalid();
      events = json.tree(eventSource);
      if (events.path("schemaVersion").asInt() != 1 || events.path("events").size() != 3) invalid();
    } catch (Exception e) { throw new DomainException(ErrorCode.RAINFALL_DATA_INVALID); }
  }

  public JsonNode catalog() { return catalog.deepCopy(); }
  public JsonNode events() { return events.deepCopy(); }
  public ObservedForcing require(String hash) {
    if (hash == null || !hash.matches("[a-f0-9]{64}"))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var value = models.get(hash);
    if (value == null) throw new DomainException(ErrorCode.MODEL_NOT_ELIGIBLE);
    return value;
  }
  private static String read(String file, int maximum) throws IOException {
    try (var input = new ClassPathResource("native-game/v2/" + file).getInputStream()) {
      byte[] raw = input.readNBytes(maximum + 1);
      if (raw.length > maximum) invalid();
      return new String(raw, StandardCharsets.UTF_8);
    }
  }
  private static void invalid() { throw new DomainException(ErrorCode.RAINFALL_DATA_INVALID); }
}
