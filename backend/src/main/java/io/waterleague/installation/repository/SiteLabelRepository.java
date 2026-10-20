package io.waterleague.installation.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.zip.GZIPInputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SiteLabelRepository {
  public static final String INDEX_SHA256 = "e9e8aea3d9a0b935b1da215dbb317cece52797df3cad51e473f90d75aff15330";
  private final JsonService json;
  private final JsonNode index;
  private final LinkedHashMap<String, JsonNode> cache = new LinkedHashMap<>(16, .75f, true);

  public SiteLabelRepository(JsonService json) {
    this.json = json;
    try (var stream = new ClassPathResource("site-labels/v1/index.json").getInputStream()) {
      String raw = new String(stream.readNBytes(262145), StandardCharsets.UTF_8);
      index = json.tree(raw);
      if (!json.hash(raw).equals(INDEX_SHA256) || index.path("schemaVersion").asInt() != 1
          || index.path("parts").size() != 256) invalid();
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  public record Label(String name, String address) {}

  public synchronized Label require(String id) {
    if (id == null || !id.matches("C[a-f0-9]{24}")) invalid();
    String prefix = id.substring(1, 3);
    try {
      JsonNode part = cache.get(prefix);
      if (part == null) {
        var entry = index.path("parts").path(prefix);
        int size = entry.path("bytes").asInt();
        if (size <= 0 || size > 2_000_000 || !entry.path("file").asString().equals(prefix + ".json.gz")) invalid();
        try (var stream = new GZIPInputStream(
            new ClassPathResource("site-labels/v1/" + prefix + ".json.gz").getInputStream())) {
          byte[] bytes = stream.readNBytes(size + 1);
          String raw = new String(bytes, StandardCharsets.UTF_8);
          if (bytes.length != size || !json.hash(raw).equals(entry.path("sha256").asString())) invalid();
          part = json.tree(raw);
          if (part.size() != entry.path("count").asInt()) invalid();
        }
        cache.put(prefix, part);
        if (cache.size() > 16) cache.remove(cache.keySet().iterator().next());
      }
      var value = part.path(id);
      String name = value.path("name").asString("");
      String address = value.path("address").isString() ? value.path("address").asString() : null;
      if (name.isBlank() || name.length() > 250 || address != null && address.length() > 300) invalid();
      return new Label(name, address);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  private static void invalid() { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
}
