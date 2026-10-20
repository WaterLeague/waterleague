package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.strategy.entity.FacilityType;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class NativeGroundLookupTests {
  private static SiteCatalogRepository sites;

  @BeforeAll
  static void catalog() {
    sites = NativeSiteFixtures.repository();
  }

  @Test
  void selectsTheOriginalCandidateAtItsExactPointAndPreservesEveryRing() throws Exception {
    var candidate = NativeSiteFixtures.cell(sites, "11680", FacilityType.PERMEABLE_PAVEMENT, 0);
    var selected = sites.ground(candidate.center().get(0), candidate.center().get(1));
    assertThat(selected.cellId()).isEqualTo(candidate.cellId());
    assertThat(selected.polygons()).isEqualTo(candidate.polygons());
    assertThat(selected.sourceIds()).allMatch(id -> id.startsWith("ngii:"));
    assertThat(selected.modelHash())
        .isEqualTo("d2d9ea2a888ee01d59f253b3848c3c30fdf4b6b3f03662b1202dc9b7a48b88b9");
    var json =
        new io.waterleague.common.service.JsonService(new tools.jackson.databind.ObjectMapper());
    io.waterleague.installation.view.SiteView reference = null;
    try (var input =
        getClass().getResourceAsStream("/infrastructure/native-v1/associations.json")) {
      var rows =
          json.tree(new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
      for (var row : rows.path("associations")) {
        var site = sites.require(row.path("districtId").asString(), row.path("cellId").asString());
        if (site.kind().equals("GROUND") && site.maxAreaM2().doubleValue() >= 30) {
          reference = site;
          break;
        }
      }
    }
    assertThat(reference).isNotNull();
    java.nio.file.Files.writeString(
        java.nio.file.Path.of("target/native-site-contract-v1.json"),
        json.write(
                java.util.Map.of(
                    "ground",
                    candidate,
                    "reference",
                    reference,
                    "roof",
                    NativeSiteFixtures.cell(sites, "11680", FacilityType.GREEN_ROOF, 0)))
            + "\n");
  }

  @Test
  void restoresParkingCandidatesWithSourceNamesAndDedicatedSurfaceFilter() {
    var parking = sites.require("11380", "Cfd3204429da79b5a6db2702b");
    assertThat(parking.name()).isEqualTo("북한산성제1주차장 · 1");
    assertThat(parking.sourceRole()).isEqualTo("PARKING_AREA");
    assertThat(parking.allowedTypes()).containsExactly("PERMEABLE_PAVEMENT");
    assertThat(sites.ground(parking.center().get(0), parking.center().get(1)).cellId())
        .isEqualTo(parking.cellId());
    var nearby = sites.nearest("11380", parking.center().get(0), parking.center().get(1),
        0, FacilityType.PERMEABLE_PAVEMENT, false,
        io.waterleague.installation.entity.SiteSurface.PARKING);
    assertThat(nearby.sites()).allMatch(site -> site.sourceRole().equals("PARKING_AREA"));
    assertThat(nearby.sites()).anyMatch(site -> site.cellId().equals(parking.cellId()));
  }

  @Test
  void rejectsNonFiniteAndOutsidePointsWithoutNearestFallback() {
    for (double x : new double[] {Double.NaN, Double.POSITIVE_INFINITY, 100001, 99999})
      assertThatThrownBy(() -> sites.ground(x, 0)).isInstanceOf(DomainException.class);
  }

  @Test
  void returnsTheCanonicalCandidateDistrictAcrossAdministrativeEdges() {
    for (var entry :
        new String[][] {
          {"11740", "C0200c7ec7a1b9b5da35791c6"},
          {"11110", "C024f3dcd1567599f45327d03"},
          {"11680", "C03e26bb0db0cfcbfec2333e3"}
        }) {
      var expected = sites.require(entry[0], entry[1]);
      var selected = sites.ground(expected.center().get(0), expected.center().get(1));
      assertThat(selected.districtId()).isEqualTo(entry[0]);
      assertThat(selected.cellId()).isEqualTo(entry[1]);
      assertThat(selected.polygons()).isEqualTo(expected.polygons());
    }
  }
}
