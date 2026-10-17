package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.floodtrace.controller.FloodTraceController;
import io.waterleague.floodtrace.repository.FloodTraceRepository;
import io.waterleague.floodtrace.service.FloodTraceService;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class FloodTraceTests {
  private final JsonService json = new JsonService(new ObjectMapper());
  private final FloodTraceService service = new FloodTraceService(new FloodTraceRepository(json));

  @Test
  void keepsSourceDatesAndUnknownsSeparateFromSimulatedWater() {
    var catalog = service.catalog().catalog();
    assertThat(catalog.usage()).isEqualTo("OBSERVED_EVENT_EXTENT_REFERENCE");
    assertThat(catalog.events()).extracting(e -> e.includedCount()).containsExactly(10412, 9590, 18286);
    var event = catalog.events().getLast();
    assertThat(event.periodStart()).isEqualTo("2022-08-08");
    assertThat(event.periodEnd()).isEqualTo("2022-08-17");
    assertThat(event.fileModifiedAt()).isEqualTo("2026-01-07");
    assertThat(event.statusCounts()).containsEntry("INCLUDED_WITHOUT_END_DATE", 9696)
        .containsEntry("INVALID_GEOMETRY", 21).containsEntry("OTHER_EVENT", 1574);
  }

  @Test
  void verifiesEveryPublishedTileAndOnlyExposesDisplayGeometry() {
    int count = 0;
    for (var event : service.catalog().catalog().events()) {
      for (var tile : event.tiles()) {
        var response = service.tile(event.id(), tile.id());
        assertThat(json.hash(response.json())).isEqualTo(tile.sha256());
        var content = json.tree(response.json());
        assertThat(content.size()).isEqualTo(4);
        assertThat(content.path("eventId").asString()).isEqualTo(event.id());
        assertThat(content.path("id").asString()).isEqualTo(tile.id());
        assertThat(content.path("triangleVertices").size() % 6).isZero();
        assertThat(content.path("path").asString()).matches("[MLZ0-9.,e+\\- ]+");
        assertThat(response.json()).doesNotContain("F_ZONE_NM", "F_AVR_HGT", "F_SHIM", "sourceProperties", "Users", "data/raw");
        count++;
      }
    }
    assertThat(count).isEqualTo(143);
    var controller = new FloodTraceController(service);
    assertThat(controller.catalog().getHeaders().getCacheControl()).contains("public", "immutable");
    assertThat(controller.catalog().getHeaders().getETag()).contains(FloodTraceRepository.SHA256);
  }

  @Test
  void rejectsUnknownEventsAndPathsBeforeReadingResources() {
    for (var request : new String[][] {{"../catalog", "0_0"}, {"seoul-20220808", "../../catalog"},
        {"seoul-20220808", "999_999"}}) {
      assertThatThrownBy(() -> service.tile(request[0], request[1]))
          .isInstanceOfSatisfying(DomainException.class,
              error -> assertThat(error.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    }
  }
}
