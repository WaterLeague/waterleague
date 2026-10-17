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
  void retainsSourceDeletionAndExcludesUnknownRowsWithoutInventingOperatingDates() throws Exception {
    var repository = new InfrastructureRepository(json);
    var view = new InfrastructureService(repository, new InfrastructureMapper()).referenceCatalog();
    assertThat(repository.records()).hasSize(1696);
    assertThat(view.assets()).hasSize(1604);
    assertThat(view.statusCounts()).containsEntry("SOURCE_DELETED", 90L)
        .containsEntry("DELETE_FLAG_UNKNOWN", 2L);
    assertThat(view.usage()).isEqualTo("REFERENCE_ONLY");
    assertThat(view.assets()).allSatisfy(a -> {
      assertThat(a.validFrom()).isNull();
      assertThat(a.validTo()).isNull();
      assertThat(a.operationStatus()).isEqualTo("UNKNOWN");
      assertThat(a.geometryEvidence()).isEqualTo("LOCATION_POINT");
      assertThat(a.hydraulicStatus()).isEqualTo("UNCONNECTED");
      assertThat(a.districtId()).isNotBlank();
    });
    assertThat(json.write(view)).doesNotContain("data/raw", "sourceProperties", "downloadForm");
    assertThat(view.sources()).hasSize(9);
    assertThat(view.sources().getFirst().path("fileModifiedAt").asString()).isEqualTo("2022-04-03");
    assertThat(view.sources().getFirst().path("portalUpdatedAt").asString()).isEqualTo("2026-10-03");
  }

  @Test
  void preservesUnitCapacityAndCountsReservoirOnceAcrossFifteenPumps() throws Exception {
    var view = new InfrastructureService(new InfrastructureRepository(json), new InfrastructureMapper()).referenceCatalog();
    var station = view.assets().stream().filter(a -> a.id().equals("15148889:가양")).findFirst().orElseThrow();
    var spec = station.pumpSpecs();
    assertThat(spec.path("asOf").asString()).isEqualTo("2025-09-08");
    assertThat(spec.path("units").size()).isEqualTo(15);
    assertThat(spec.path("storageCapacityM3").asDouble()).isEqualTo(90000);
    assertThat(spec.path("basinAreaHa").asDouble()).isEqualTo(578);
    assertThat(spec.path("units").get(0).path("capacityM3Min").asDouble()).isEqualTo(405);
    assertThat(spec.path("units").get(10).path("capacityM3Min").asDouble()).isEqualTo(320);
    assertThat(station.center().get(0)).isBetween(-10500.0, -9800.0);
  }
}
