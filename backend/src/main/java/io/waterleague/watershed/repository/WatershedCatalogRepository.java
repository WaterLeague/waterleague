package io.waterleague.watershed.repository;

import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class WatershedCatalogRepository {
  public static final String HASH =
      "beaddba8868b6f1f6bbf35b1d53d4695a94db99498d8988f90d62013cf8f053c";
  public static final String LAYOUT_HASH =
      "fa3e4d833650df5c40d933bd0b289dd029a54e0beb73fad9b9d3ef239cb0236d";
  public static final String STORAGE_HASH =
      "f2df891f3914de02c37ff7ae09f6d5a849ef6f69dae85e25e562e5a44cffc105";
  public static final String CONDUIT_HASH =
      "a5dac5d1552b1620bfbe65c2f54a62626de16dd70a3807b1a2d03736ddcfdd6b";
  private final JsonNode conduits;
  private final JsonNode storage;
  private final JsonNode catalog;
  private final JsonNode layout;

  public WatershedCatalogRepository(JsonService json) throws java.io.IOException {
    conduits = load(json, "watersheds/seocho-conduits-v1.json", CONDUIT_HASH);
    if (!conduits.path("sourceCatalogSha256").asString().equals(HASH))
      throw new IllegalStateException("관로 원본 불일치");
    storage = load(json, "watersheds/seocho-storage-connections-v1.json", STORAGE_HASH);
    catalog = load(json, "watersheds/seocho-published-v1.json", HASH);
    layout = load(json, "watersheds/seocho-layout-v1.json", LAYOUT_HASH);
    if (!storage.path("sourceCatalogSha256").asString().equals(HASH))
      throw new IllegalStateException("저류조 연결 원본 불일치");
    if (!layout.path("sourceOriginalSha256").equals(catalog.path("sourceOriginalSha256")))
      throw new IllegalStateException("관망 표시 원본 불일치");
  }

  private JsonNode load(JsonService json, String path, String hash) throws java.io.IOException {
    try (var in = new ClassPathResource(path).getInputStream()) {
      byte[] bytes = in.readNBytes(65537);
      String raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > 65536 || !json.hash(raw).equals(hash))
        throw new IllegalStateException("공개 관망 목록 무결성 오류");
      return json.tree(raw);
    }
  }

  public JsonNode conduits() {
    return conduits.deepCopy();
  }

  public JsonNode storage() {
    return storage.deepCopy();
  }

  public JsonNode value() {
    return catalog.deepCopy();
  }

  public JsonNode layout() {
    return layout.deepCopy();
  }
}
