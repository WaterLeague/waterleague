package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.infrastructure.mapper.InfrastructureMapper;
import io.waterleague.infrastructure.repository.InfrastructureRepository;
import io.waterleague.infrastructure.service.InfrastructureService;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class InfrastructureCatalogTests {
  private final JsonService json = new JsonService(new ObjectMapper());

  @Test
  void retainsSourceDeletionAndExcludesUnknownRowsWithoutInventingOperatingDates()
      throws Exception {
    var repository = new InfrastructureRepository(json);
    var view = new InfrastructureService(repository, new InfrastructureMapper()).referenceCatalog();
    assertThat(repository.records()).hasSize(1707);
    assertThat(view.assets()).hasSize(1615);
    assertThat(view.statusCounts())
        .containsEntry("SOURCE_DELETED", 90L)
        .containsEntry("DELETE_FLAG_UNKNOWN", 2L);
    assertThat(view.usage()).isEqualTo("REFERENCE_ONLY");
    assertThat(view.assets())
        .allSatisfy(
            a -> {
              assertThat(a.validFrom()).isNull();
              assertThat(a.validTo()).isNull();
              assertThat(a.operationStatus()).isEqualTo("UNKNOWN");
              assertThat(a.geometryEvidence())
                  .isEqualTo(
                      a.footprint() == null
                          ? "LOCATION_POINT"
                          : a.footprint().has("buildingId")
                              ? "PUBLIC_MAPPED_BUILDING"
                              : "PUBLIC_MAPPED_FOOTPRINT");
              assertThat(a.hydraulicStatus()).isEqualTo("UNCONNECTED");
              assertThat(a.districtId()).isNotBlank();
            });
    assertThat(json.write(view)).doesNotContain("data/raw", "sourceProperties", "downloadForm");
    assertThat(view.sources()).hasSize(11);
    assertThat(view.sources().getFirst().path("fileModifiedAt").asString()).isEqualTo("2022-04-03");
    assertThat(view.sources().getFirst().path("portalUpdatedAt").asString())
        .isEqualTo("2026-10-03");
  }

  @Test
  void mappedBasinsPreserveGeometryWithoutInventingCapacityOrHistoricalExistence()
      throws Exception {
    var view =
        new InfrastructureService(new InfrastructureRepository(json), new InfrastructureMapper())
            .referenceCatalog();
    var basins = view.assets().stream().filter(a -> a.kind().equals("RETENTION_BASIN")).toList();
    assertThat(basins).hasSize(3);
    assertThat(basins)
        .allSatisfy(
            a -> {
              assertThat(a.kind()).isEqualTo("RETENTION_BASIN");
              assertThat(a.verticalLayer()).isEqualTo("MAPPED_SURFACE");
              assertThat(a.pumpSpecs().isNull()).isTrue();
              assertThat(a.footprint().path("polygons").size()).isPositive();
              assertThat(a.footprint().path("areaM2").asDouble()).isPositive();
              assertThat(a.footprint().path("basis").asString())
                  .isEqualTo("PUBLIC_OSM_MAPPING_NOT_SURVEYED_OR_AS_BUILT");
            });
  }

  @Test
  void preservesUnitCapacityAndCountsReservoirOnceAcrossFifteenPumps() throws Exception {
    var view =
        new InfrastructureService(new InfrastructureRepository(json), new InfrastructureMapper())
            .referenceCatalog();
    var station =
        view.assets().stream().filter(a -> a.id().equals("15148889:가양")).findFirst().orElseThrow();
    var spec = station.pumpSpecs();
    assertThat(spec.path("asOf").asString()).isEqualTo("2025-09-08");
    assertThat(spec.path("units").size()).isEqualTo(15);
    assertThat(spec.path("storageCapacityM3").asDouble()).isEqualTo(90000);
    assertThat(spec.path("basinAreaHa").asDouble()).isEqualTo(578);
    assertThat(spec.path("units").get(0).path("capacityM3Min").asDouble()).isEqualTo(405);
    assertThat(spec.path("units").get(10).path("capacityM3Min").asDouble()).isEqualTo(320);
    assertThat(station.center().get(0)).isBetween(-10500.0, -9800.0);
  }

  @Test
  void preservesPreviousCatalogAndMapsEightExplicitPumpBuildingsWithoutHistoricalClaims()
      throws Exception {
    var repository = new InfrastructureRepository(json);
    var service = new InfrastructureService(repository, new InfrastructureMapper());
    var old = service.referenceCatalog(true);
    assertThat(old.version()).isEqualTo("seoul-public-20261018-v2");
    assertThat(old.sha256()).isEqualTo(InfrastructureRepository.V2_SHA256);
    assertThat(old.assets()).hasSize(1607);
    assertThat(service.referenceCatalog().assets()).containsAll(old.assets());
    var buildings =
        service.referenceCatalog().assets().stream()
            .filter(a -> a.geometryEvidence().equals("PUBLIC_MAPPED_BUILDING"))
            .toList();
    assertThat(buildings)
        .hasSize(8)
        .allSatisfy(
            a -> {
              assertThat(a.footprint().path("buildingId").asString()).startsWith("W");
              assertThat(a.footprint().path("heightBasis").asString())
                  .isEqualTo("EXISTING_CITY_DISPLAY_ASSUMPTION");
              assertThat(a.validFrom()).isNull();
              assertThat(a.hydraulicStatus()).isEqualTo("UNCONNECTED");
            });
    var policy = new io.waterleague.infrastructure.repository.SurfaceOccupancyRepository(json);
    for (var building : buildings) {
      String cell = "R" + building.footprint().path("buildingId").asString();
      assertThatThrownBy(() -> policy.exclusion(building.districtId(), cell, "wrong-hash", "ROOF"))
          .isInstanceOf(IllegalStateException.class);
    }
  }
}
