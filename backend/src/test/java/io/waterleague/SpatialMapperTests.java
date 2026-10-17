package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.spatial.entity.SpatialSnapshot;
import io.waterleague.spatial.mapper.SpatialMapper;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class SpatialMapperTests {
  private final SpatialMapper mapper = new SpatialMapper(new ObjectMapper());
  // 운영 자료와 분리한 계약 시험 도형.
  private final String sample =
      """
      {"schemaVersion":1,"provider":"국토지리정보원","layer":"N1A_B0010000",
      "requestedCrs":"EPSG:4326","sourceUrl":"https://www.data.go.kr/data/15059719/fileData.do",
      "retrievedAt":"2026-10-17T00:00:00Z","dataYear":2025,"use":"DISPLAY_COMPARISON_ONLY",
      "rawRetained":true,"bounds":[127.0525,37.543,127.0555,37.5455],
      "buildings":[{"id":"test-1","name":"시험 건물","aboveGroundFloors":5,
      "polygons":[[[[127.054,37.544],[127.0541,37.544],[127.0541,37.5441],[127.054,37.544]]]]}]}
      """;

  private SpatialSnapshot snapshot(String raw) {
    return new SpatialSnapshot(raw, "a".repeat(64));
  }

  @Test
  void preservesFrozenProvenanceAndUnknownFloorWithoutInventingHeight() {
    var view = mapper.map(snapshot(sample));
    assertThat(view.buildings().getFirst().aboveGroundFloors()).isEqualTo(5);
    assertThat(view.use()).isEqualTo("DISPLAY_COMPARISON_ONLY");
    assertThat(view.rawRetained()).isTrue();
    assertThat(view.retrievedAt()).hasToString("2026-10-17T00:00:00Z");
    assertThat(view.snapshotHash()).isEqualTo("a".repeat(64));
    assertThat(mapper.map(snapshot(sample))).isEqualTo(view);
    assertThat(
            mapper
                .map(snapshot(sample.replace("Floors\":5", "Floors\":null")))
                .buildings()
                .getFirst()
                .aboveGroundFloors())
        .isNull();
    assertThatThrownBy(() -> view.buildings().clear())
        .isInstanceOf(UnsupportedOperationException.class);
    assertThatThrownBy(() -> view.buildings().getFirst().polygons().getFirst().getFirst().clear())
        .isInstanceOf(UnsupportedOperationException.class);
  }

  @Test
  void rejectsBrokenGeometryAndProvenance() {
    var invalid =
        new String[] {
          sample.replace("127.0541", "14144000"),
          sample.replace("[127.054,37.544]]]]", "[127.055,37.544]]]]"),
          sample.replace("Floors\":5", "Floors\":0"),
          sample.replace("Floors\":5", "Floors\":1.5"),
          sample.replace("Floors\":5", "Floors\":201"),
          sample.replace("Floors\":5", "Floors\":\"5\""),
          sample.replace("EPSG:4326", "EPSG:5186"),
          sample.replace("2025", "2024"),
          sample.replace("DISPLAY_COMPARISON_ONLY", "CALIBRATED"),
          sample.replace("rawRetained\":true", "rawRetained\":false"),
          sample.replace("127.0525", "127.0425"),
          sample.replace("N1A_B0010000", "LT_C_SPBD"),
          "secret-provider-url"
        };
    for (var raw : invalid) {
      assertThatThrownBy(() -> mapper.map(snapshot(raw)))
          .isInstanceOf(DomainException.class)
          .hasMessageNotContaining("secret-provider-url");
    }
  }

  @Test
  void rejectsDuplicateBuildingIds() {
    var json = new ObjectMapper();
    var tree = json.readTree(sample);
    ((tools.jackson.databind.node.ArrayNode) tree.path("buildings"))
        .add(tree.path("buildings").get(0));
    assertThatThrownBy(() -> mapper.map(snapshot(json.writeValueAsString(tree))))
        .isInstanceOf(DomainException.class);
  }
}
