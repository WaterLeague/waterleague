package io.waterleague.installation.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.infrastructure.repository.SurfaceOccupancyRepository;
import io.waterleague.installation.entity.SiteSurface;
import io.waterleague.installation.view.*;
import io.waterleague.spatial.repository.NativePlayRepository;
import io.waterleague.spatial.service.NativeGeometry;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SiteCatalogRepository {
  public static final double ORIGIN_X = 198128, ORIGIN_Y = 551989;
  private final NativePlayRepository nativeSites;
  private final DistrictRepository districts;
  private final SurfaceOccupancyRepository references;
  private final JsonService json;
  private final SiteLabelRepository labels;

  public SiteCatalogRepository(
      JsonService json,
      DistrictRepository districts,
      NativePlayRepository nativeSites,
      SurfaceOccupancyRepository references,
      SiteLabelRepository labels) {
    this.json = json;
    this.districts = districts;
    this.nativeSites = nativeSites;
    this.references = references;
    this.labels = labels;
  }

  public Map<String, Integer> counts() {
    return nativeSites.supportedCounts();
  }

  public Map<String, String> versions() {
    var values = new TreeMap<String, String>();
    districts.all().forEach(district -> values.put(district.id(), nativeSites.sha256()));
    return Map.copyOf(values);
  }

  public SitePageView nearest(
      String districtId,
      double x,
      double y,
      int offset,
      FacilityType type,
      boolean vacant,
      SiteSurface surface) {
    districts.require(districtId);
    String role = surface == null ? null : surface.nativeRole();
    var result =
        nativeSites.nearest(
            districtId,
            x + ORIGIN_X,
            y + ORIGIN_Y,
            offset,
            type == null ? null : 1 << type.ordinal(),
            role);
    var metadata = nativeSites.metadata();
    return new SitePageView(
        result.cells().stream().map(cell -> view(cell, metadata)).toList(),
        counts(),
        result.count(),
        offset,
        200);
  }

  public SiteView building(String districtId, String sourceId) {
    districts.require(districtId);
    return view(nativeSites.building(districtId, sourceId), nativeSites.metadata());
  }

  public SiteView ground(double x, double y) {
    if (!Double.isFinite(x) || !Double.isFinite(y) || Math.abs(x) > 100000 || Math.abs(y) > 100000)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var cell = nativeSites.atPoint(x + ORIGIN_X, y + ORIGIN_Y, "GROUND");
    return view(cell, nativeSites.metadata());
  }

  public SiteView require(String districtId, String cellId) {
    districts.require(districtId);
    var cell = nativeSites.require(districtId, cellId);
    if (cell.path("allowedTypes").isEmpty()) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    return view(cell, nativeSites.metadata());
  }

  public SiteView requireInstallable(String districtId, String cellId) {
    return require(districtId, cellId);
  }

  public JsonNode publicAssetPolicy() {
    return references.evidence();
  }

  private SiteView view(JsonNode cell, JsonNode metadata) {
    NativeGeometry.polygon(cell.path("geometry"), cell.path("areaM2").asDouble());
    var components = new ArrayList<List<List<List<Double>>>>();
    var geometry = cell.path("geometry");
    var source =
        geometry.path("type").asString().equals("Polygon")
            ? List.of(geometry.path("coordinates"))
            : iterable(geometry.path("coordinates"));
    for (var part : source) {
      var rings = new ArrayList<List<List<Double>>>();
      for (var ring : part) {
        var points = new ArrayList<List<Double>>();
        for (var point : ring)
          points.add(
              List.of(point.get(0).asDouble() - ORIGIN_X, point.get(1).asDouble() - ORIGIN_Y));
        rings.add(List.copyOf(points));
      }
      components.add(List.copyOf(rings));
    }
    var costs = new LinkedHashMap<String, BigDecimal>();
    for (var type : FacilityType.values())
      costs.put(type.name(), metadata.path("unitCosts").path(type.name()).decimalValue());
    var types = iterable(cell.path("allowedTypes")).stream().map(JsonNode::asString).toList();
    var sourceIds = iterable(cell.path("sourceIds")).stream().map(JsonNode::asString).toList();
    var center = cell.path("centerProjected");
    String districtId = cell.path("districtId").asString(), id = cell.path("id").asString();
    var label = cell.path("displayName").isString()
        ? new SiteLabelRepository.Label(cell.path("displayName").asString(), null)
        : labels.require(id);
    return new SiteView(
        districtId,
        id,
        label.name(),
        cell.path("kind").asString(),
        List.copyOf(components),
        List.of(center.get(0).asDouble() - ORIGIN_X, center.get(1).asDouble() - ORIGIN_Y),
        cell.path("heightM").asDouble(),
        cell.path("areaM2").asDouble(),
        cell.path("maxAreaM2").decimalValue(),
        types,
        Map.copyOf(costs),
        nativeSites.sha256(),
        sourceIds,
        cell.path("areaLimitBasis").asString(),
        cell.path("siteEligibility").asString(),
        cell.path("inflowPolicy").asString(),
        metadata.path("costModel").deepCopy(),
        metadata.path("costSourceSha256").asString(),
        cell.path("physicalInputs").deepCopy(),
        metadata.path("facilityDesignSet").deepCopy(),
        metadata.path("initializationPolicy").deepCopy(),
        null,
        cell.path("role").asString(),
        references.forCandidate(districtId, id),
        label.address());
  }

  private static List<JsonNode> iterable(JsonNode value) {
    var result = new ArrayList<JsonNode>();
    value.forEach(result::add);
    return List.copyOf(result);
  }
}
