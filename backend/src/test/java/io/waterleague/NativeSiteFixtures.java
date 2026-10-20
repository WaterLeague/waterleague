package io.waterleague;

import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.infrastructure.repository.SurfaceOccupancyRepository;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.repository.SiteLabelRepository;
import io.waterleague.installation.view.SiteView;
import io.waterleague.rainfall.repository.ObservedGameRepository;
import io.waterleague.spatial.repository.NativePlayBundle;
import io.waterleague.spatial.repository.NativePlayRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.util.*;
import tools.jackson.databind.ObjectMapper;

final class NativeSiteFixtures {
  private static final Map<String, Map<String, SiteView>> CACHE = new HashMap<>();

  static SiteCatalogRepository repository() {
    try {
      var json = new JsonService(new ObjectMapper());
      var observations = new ObservedGameRepository(json);
      var nativeSites =
          new NativePlayRepository(new NativePlayBundle(json, "../tmp/native-spatial"), json);
      return new SiteCatalogRepository(
          json,
          new DistrictRepository(json, observations),
          nativeSites,
          new SurfaceOccupancyRepository(json),
          new SiteLabelRepository(json));
    } catch (Exception e) {
      throw new IllegalStateException("원형 시험 카탈로그 읽기 실패", e);
    }
  }

  static SiteView cell(
      SiteCatalogRepository repository, String district, FacilityType type, int index) {
    return sites(repository, district).values().stream()
        .filter(
            site ->
                site.allowedTypes().contains(type.name()) && site.maxAreaM2().doubleValue() >= 30)
        .skip(index)
        .findFirst()
        .orElseThrow();
  }

  static SiteView reference(SiteCatalogRepository repository) throws Exception {
    var json = new JsonService(new ObjectMapper());
    try (var input =
        NativeSiteFixtures.class.getResourceAsStream(
            "/infrastructure/native-v1/associations.json")) {
      var root =
          json.tree(new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
      for (var row : root.path("associations")) {
        var site =
            repository.require(row.path("districtId").asString(), row.path("cellId").asString());
        if (site.kind().equals("GROUND") && site.maxAreaM2().doubleValue() >= 30) return site;
      }
    }
    throw new IllegalStateException("공개 위치점의 원형 지상 후보 누락");
  }

  static synchronized Map<String, SiteView> sites(
      SiteCatalogRepository repository, String district) {
    return CACHE.computeIfAbsent(
        district,
        id -> {
          var values = new LinkedHashMap<String, SiteView>();
          for (var type : FacilityType.values())
            repository
                .nearest(id, 0, 0, 0, type, false, null)
                .sites()
                .forEach(site -> values.put(site.cellId(), site));
          var json = new JsonService(new ObjectMapper());
          var nativeSites =
              new NativePlayRepository(new NativePlayBundle(json, "../tmp/native-spatial"), json);
          try (var connection = nativeSites.connection();
              var query =
                  connection.prepareStatement(
                      "SELECT id FROM sites WHERE district_id=? AND kind='ROOF' AND allowed_mask<>0"
                          + " ORDER BY CAST(json_extract(body,'$.maxAreaM2') AS REAL) DESC,id LIMIT"
                          + " 20")) {
            query.setString(1, id);
            try (var rows = query.executeQuery()) {
              while (rows.next()) {
                var site = repository.require(id, rows.getString(1));
                values.put(site.cellId(), site);
              }
            }
          } catch (Exception e) {
            throw new IllegalStateException("큰 원형 옥상 시험 후보 조회 실패", e);
          }
          return Collections.unmodifiableMap(values);
        });
  }

  private NativeSiteFixtures() {}
}
