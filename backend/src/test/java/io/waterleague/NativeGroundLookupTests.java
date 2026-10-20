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
    var selected =
        sites.ground(candidate.districtId(), candidate.center().get(0), candidate.center().get(1));
    assertThat(selected.cellId()).isEqualTo(candidate.cellId());
    assertThat(selected.polygons()).isEqualTo(candidate.polygons());
    assertThat(selected.sourceIds()).allMatch(id -> id.startsWith("ngii:"));
    assertThat(selected.modelHash())
        .isEqualTo("4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7");
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
  void rejectsNonFiniteOutsideAndOtherDistrictPointsWithoutNearestFallback() {
    for (double x : new double[] {Double.NaN, Double.POSITIVE_INFINITY, 100001, 99999})
      assertThatThrownBy(() -> sites.ground("11680", x, 0)).isInstanceOf(DomainException.class);
    var candidate = NativeSiteFixtures.cell(sites, "11680", FacilityType.PERMEABLE_PAVEMENT, 0);
    assertThatThrownBy(
            () -> sites.ground("11200", candidate.center().get(0), candidate.center().get(1)))
        .isInstanceOf(DomainException.class);
  }
}
