package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import java.util.HashSet;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WatershedLayoutTests {
  @Test
  void bindsRoadSupportedLocationWithoutChangingSourceOrRankingEligibility() throws Exception {
    var catalog = new WatershedCatalogRepository(new JsonService(new ObjectMapper()));
    var geo = catalog.georeference();
    assertThat(geo.path("sourceCrsVerified").asBoolean()).isFalse();
    assertThat(geo.path("sourceLayoutSha256").asString())
        .isEqualTo(WatershedCatalogRepository.LAYOUT_HASH);
    assertThat(catalog.value().path("horizontalCrs").isNull()).isTrue();
    assertThat(catalog.value().path("rankingEligible").asBoolean()).isFalse();
    assertThat(geo.path("nodes")).hasSize(28);
    assertThat(geo.path("links")).hasSize(26);
    assertThat(geo.path("catchments")).hasSize(14);
    for (int i = 0; i < geo.path("nodes").size(); i++) {
      var before = catalog.layout().path("nodes").get(i);
      var after = geo.path("nodes").get(i);
      assertThat(after.path("id")).isEqualTo(before.path("id"));
      assertThat(after.path("coordinate").get(0).asDouble())
          .isCloseTo(before.path("coordinate").get(0).asDouble(), within(0.000001));
      assertThat(after.path("coordinate").get(1).asDouble())
          .isCloseTo(before.path("coordinate").get(1).asDouble() + 100000, within(0.000001));
    }
  }

  @Test
  void preservesSourceCatchmentsAndTheirCalculationOutlets() throws Exception {
    var catalog = new WatershedCatalogRepository(new JsonService(new ObjectMapper()));
    var layout = catalog.layout();
    assertThat(layout.path("sourceOriginalSha256"))
        .isEqualTo(catalog.value().path("sourceOriginalSha256"));
    assertThat(layout.path("horizontalCrs").isNull()).isTrue();
    assertThat(layout.path("nodes")).hasSize(28);
    assertThat(layout.path("links")).hasSize(26);
    var expected = new HashSet<String>();
    for (var c : catalog.value().path("catchments"))
      expected.add(c.path("id").asString() + ":" + c.path("outletNodeId").asString());
    var displayed = new HashSet<String>();
    for (var c : layout.path("catchments")) {
      displayed.add(c.path("id").asString() + ":" + c.path("outletNodeId").asString());
      assertThat(c.path("points").size()).isGreaterThanOrEqualTo(3);
    }
    assertThat(displayed).hasSize(14).isEqualTo(expected);
  }
}
