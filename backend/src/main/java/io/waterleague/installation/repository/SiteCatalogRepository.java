package io.waterleague.installation.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.installation.view.SiteView;
import io.waterleague.model.repository.LabModelRepository;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.GZIPInputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SiteCatalogRepository {
  private final JsonService json;
  private final DistrictRepository districts;
  private final LabModelRepository models;
  private final io.waterleague.infrastructure.repository.SurfaceOccupancyRepository occupancy;
  private final Map<String, JsonNode> entries = new LinkedHashMap<>();
  private final Map<String, JsonNode> streetEntries = new LinkedHashMap<>();
  private final Map<String, Integer> counts = new LinkedHashMap<>();
  private final Map<String, Map<String, SiteView>> cache = new LinkedHashMap<>(8, .75f, true);

  public SiteCatalogRepository(
      JsonService json,
      DistrictRepository districts,
      LabModelRepository models,
      io.waterleague.infrastructure.repository.SurfaceOccupancyRepository occupancy)
      throws IOException {
    this.json = json;
    this.districts = districts;
    this.models = models;
    this.occupancy = occupancy;
    var source = read("catalog-v9.json", false, 50000);
    if (!json.hash(source)
        .equals("2c01768343c093e3afb21fa64c8e298cb79d2cb9371442be7a092ab63c9645de"))
      throw new IllegalStateException("공동 후보 목록 해시 오류");
    for (var entry : json.tree(source).path("entries")) {
      String id = entry.path("districtId").asString();
      var district = districts.require(id);
      if (entries.put(id, entry) != null
          || !entry.path("file").asString().equals(id + "-v9.json.gz"))
        throw new IllegalStateException("공동 후보 목록 오류");
      counts.put(id, entry.path("count").asInt());
    }
    if (entries.size() != 25) throw new IllegalStateException("공동 후보 구 누락");
    var streets = read("catalog-v10.json", false, 50000);
    if (!json.hash(streets)
        .equals("2011b5356cf7885b8dbaa2f5e55446b71e82384023f98594e287f832574e5b42"))
      throw new IllegalStateException("도로 후보 목록 해시 오류");
    for (var entry : json.tree(streets).path("entries")) {
      String id = entry.path("districtId").asString();
      districts.require(id);
      if (streetEntries.put(id, entry) != null
          || !entry.path("file").asString().equals(id + "-v10.json.gz"))
        throw new IllegalStateException("도로 후보 목록 오류");
      counts.compute(id, (key, count) -> count + entry.path("count").asInt());
    }
    if (streetEntries.size() != 25) throw new IllegalStateException("도로 후보 구 누락");
  }

  private String read(String name, boolean zipped, int max) throws IOException {
    try (var source = new ClassPathResource("shared-sites/" + name).getInputStream();
        var input = zipped ? new GZIPInputStream(source) : source) {
      var bytes = input.readNBytes(max + 1);
      if (bytes.length > max) throw new IOException("공동 후보 크기 초과");
      return new String(bytes, StandardCharsets.UTF_8);
    }
  }

  public Map<String, Integer> counts() {
    return Collections.unmodifiableMap(counts);
  }

  public Map<String, String> versions() {
    var result = new TreeMap<String, String>();
    entries.forEach((id, entry) -> result.put(id, entry.path("sha256").asString()));
    streetEntries.forEach(
        (id, entry) -> result.put(id + ":streets", entry.path("sha256").asString()));
    return Collections.unmodifiableMap(result);
  }

  public synchronized Map<String, SiteView> district(String id) {
    var cached = cache.get(id);
    if (cached != null) return cached;
    var d = districts.require(id);
    var values = new LinkedHashMap<String, SiteView>();
    for (var entry : List.of(entries.get(id), streetEntries.get(id))) {
      try {
        String raw = read(entry.path("file").asString(), true, 64 * 1024 * 1024);
        String hash = entry.path("sha256").asString();
        var snapshot = json.tree(raw);
        if (!json.hash(raw).equals(hash)
            || !snapshot.path("districtId").asString().equals(id)
            || !snapshot.path("baseModelHash").asString().equals(d.modelHash()))
          throw new IllegalStateException("공동 후보 무결성 오류");
        append(values, id, snapshot, hash, List.of(0., 0.));
      } catch (IOException e) {
        throw new IllegalStateException("공동 후보 읽기 오류");
      }
    }
    if (values.size() != counts.get(id)) throw new IllegalStateException("공동 후보 개수 오류");
    var result = Collections.unmodifiableMap(values);
    cache.put(id, result);
    while (cache.size() > 4) cache.remove(cache.keySet().iterator().next());
    return result;
  }

  private void append(
      Map<String, SiteView> output,
      String districtId,
      JsonNode model,
      String hash,
      List<Double> origin) {
    var costs = new LinkedHashMap<String, BigDecimal>();
    for (var t : io.waterleague.strategy.entity.FacilityType.values())
      costs.put(t.name(), model.path("unitCosts").path(t.name()).decimalValue());
    for (var cell : model.path("cells")) {
      var coordinates = new ArrayList<List<Double>>();
      for (var p : cell.path("coordinates"))
        coordinates.add(
            List.of(p.get(0).asDouble() + origin.get(0), p.get(1).asDouble() + origin.get(1)));
      var types = new ArrayList<String>();
      for (var t : cell.path("allowedTypes")) types.add(t.asString());
      var sources = new ArrayList<String>();
      for (var source : cell.path("sourceIds")) sources.add(source.asString());
      if (sources.isEmpty() && cell.has("buildingId"))
        sources.add(cell.path("buildingId").asString());
      var site =
          new SiteView(
              districtId,
              cell.path("id").asString(),
              cell.path("name").asString(),
              cell.path("kind").asString(),
              List.copyOf(coordinates),
              List.of(
                  cell.path("center").get(0).asDouble() + origin.get(0),
                  cell.path("center").get(1).asDouble() + origin.get(1)),
              cell.path("heightM").asDouble(),
              cell.path("areaM2").asDouble(),
              cell.path("maxAreaM2").decimalValue(),
              List.copyOf(types),
              Map.copyOf(costs),
              hash,
              List.copyOf(sources),
              cell.path("areaLimitBasis").asString(),
              cell.path("siteEligibility").asString(),
              cell.path("inflowPolicy").asString(),
              model.path("costModel"),
              model.path("costSourceSha256").asString(),
              cell.path("physicalInputs"),
              model.path("facilityDesignSet"),
              model.path("initializationPolicy"),
              occupancy.exclusion(
                  districtId, cell.path("id").asString(), hash, cell.path("kind").asString()));
      if (output.put(site.cellId(), site) != null) throw new IllegalStateException("공동 후보 중복");
    }
  }

  public SiteView building(String districtId, String sourceId) {
    if (sourceId == null || !sourceId.matches("(way|relation)/[0-9]{1,16}"))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    return district(districtId).values().stream()
        .filter(s -> s.kind().equals("ROOF") && s.sourceIds().contains(sourceId))
        .findFirst()
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  public SiteView street(String districtId, String sourceId, double x, double y) {
    if (sourceId == null
        || !sourceId.matches("way/[0-9]{1,16}:[0-9]{1,6}")
        || !Double.isFinite(x)
        || !Double.isFinite(y)
        || Math.abs(x) > 100000
        || Math.abs(y) > 100000) throw new DomainException(ErrorCode.REQUEST_INVALID);
    return district(districtId).values().stream()
        .filter(
            s ->
                sourceId.equals(
                    s.physicalInputs().path("streetPlacement").path("streetId").asString()))
        .filter(s -> Math.hypot(s.center().get(0) - x, s.center().get(1) - y) <= 30)
        .min(
            Comparator.comparingDouble(
                    (SiteView s) -> Math.hypot(s.center().get(0) - x, s.center().get(1) - y))
                .thenComparing(SiteView::cellId))
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  public SiteView require(String districtId, String cellId) {
    var site = district(districtId).get(cellId);
    if (site == null) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    return site;
  }

  public SiteView requireInstallable(String districtId, String cellId) {
    var site = require(districtId, cellId);
    if (site.existingInfrastructure() != null)
      throw new DomainException(ErrorCode.EXISTING_INFRASTRUCTURE);
    return site;
  }

  public JsonNode publicAssetPolicy() {
    return occupancy.evidence();
  }
}
