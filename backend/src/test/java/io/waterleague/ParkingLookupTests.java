package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.infrastructure.repository.SurfaceOccupancyRepository;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.model.repository.LabModelRepository;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class ParkingLookupTests {
  private static SiteCatalogRepository sites;

  @BeforeAll
  static void catalog() throws Exception {
    var json = new JsonService(new ObjectMapper());
    var models = new LabModelRepository(json);
    sites = new SiteCatalogRepository(json, new DistrictRepository(json, models), models,
        new SurfaceOccupancyRepository(json));
  }

  @Test
  void selectsSamePublicParkingNearClickWithoutChangingSite() {
    var candidate = sites.district("2410520").values().stream()
        .filter(s -> s.kind().equals("GROUND") && s.sourceIds().contains("way/601312744"))
        .findFirst().orElseThrow();
    var result = sites.parking(candidate.districtId(), "way/601312744",
        candidate.center().get(0), candidate.center().get(1));
    assertThat(result).isEqualTo(candidate);
    assertThat(result.allowedTypes()).contains("PERMEABLE_PAVEMENT");
  }

  @Test
  void rejectsBadSourcesCoordinatesAndDistantOrOtherDistrictParking() {
    for (String source : new String[] {"../secret", "way/601312744:0", "not-a-source"})
      assertThatThrownBy(() -> sites.parking("2410520", source, 0, 0))
          .isInstanceOf(DomainException.class);
    for (double x : new double[] {Double.NaN, Double.POSITIVE_INFINITY, 100001})
      assertThatThrownBy(() -> sites.parking("2410520", "way/601312744", x, 0))
          .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> sites.parking("2410520", "way/601312744", 99999, 99999))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> sites.parking("2419953", "way/601312744", 7880, -6550))
        .isInstanceOf(DomainException.class);
  }
}
