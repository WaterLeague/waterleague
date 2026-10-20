package io.waterleague.cost.repository;

import io.waterleague.common.service.JsonService;
import io.waterleague.cost.exception.CostException;
import io.waterleague.installation.view.SiteView;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

@Repository
public class GamePriceCatalog {
  public static final String SHA256 =
      "00b489edc185338156d660e16aca57bd3890f1314110c4db6b6e191044f22cb3";
  private final JsonService json;
  private final JsonNode catalog;

  public GamePriceCatalog(JsonService json) {
    this.json = json;
    try (var stream =
        new ClassPathResource("facilities/game-prices-202608-v1.json").getInputStream()) {
      String raw = new String(stream.readNBytes(131073), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(SHA256)) throw new CostException();
      catalog = json.tree(raw);
    } catch (IOException e) {
      throw new CostException();
    }
  }

  public String previousVersion() {
    return catalog.path("previousCostSourceSha256").asString();
  }

  private JsonNode version(String sha) {
    var value = sha == null ? null : catalog.path("versions").get(sha);
    if (value == null || !value.isObject()) throw new CostException();
    return value;
  }

  public JsonNode metadata(JsonNode source) {
    var original = version(source.path("costSourceSha256").asString());
    if (!original.path("unitCosts").equals(source.path("unitCosts"))
        || !original.path("costModel").equals(source.path("costModel"))) throw new CostException();
    return replace(
        (ObjectNode) source.deepCopy(), catalog.path("currentCostSourceSha256").asString());
  }

  private ObjectNode replace(ObjectNode target, String sha) {
    var costs = version(sha);
    target.set("unitCosts", costs.path("unitCosts").deepCopy());
    target.set("costModel", costs.path("costModel").deepCopy());
    target.put("costSourceSha256", sha);
    return target;
  }

  public SiteView site(SiteView current, String sha) {
    // 원가만 허용 목록으로 복원하며 형상·설치 적합성은 현재 검증값을 유지한다.
    return json.read(
        json.write(replace((ObjectNode) json.tree(json.write(current)), sha)), SiteView.class);
  }
}
