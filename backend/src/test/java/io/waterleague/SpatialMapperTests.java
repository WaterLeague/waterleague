package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.DomainException;
import io.waterleague.spatial.mapper.SpatialMapper;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class SpatialMapperTests {
  private final SpatialMapper mapper = new SpatialMapper(new ObjectMapper());
  // API 응답 구조 시험용 가상 도형. 브이월드 원본이 아니다.
  private final String sample =
      """
      {"response":{"status":"OK","record":{"total":"1","current":"1"},
      "result":{"featureCollection":{"features":[{"id":"test-1","properties":
      {"buld_nm":"시험 건물","gro_flo_co":"5"},"geometry":{"type":"MultiPolygon",
      "coordinates":[[[[127.054,37.544],[127.0541,37.544],[127.0541,37.5441],[127.054,37.544]]]]}}]}}}}
      """;

  @Test
  void preservesFloorMetadataWithoutInventingHeight() {
    var view = mapper.map(sample);
    assertThat(view.buildings().getFirst().aboveGroundFloors()).isEqualTo(5);
    assertThat(view.use()).isEqualTo("DISPLAY_COMPARISON_ONLY");
    assertThat(view.rawRetained()).isFalse();
    assertThat(
            mapper.map(sample.replace("\"5\"", "\"0\"")).buildings().getFirst().aboveGroundFloors())
        .isNull();
  }

  @Test
  void rejectsIncompletePageAndOutOfRegionCoordinates() {
    assertThatThrownBy(() -> mapper.map(sample.replace("\"total\":\"1\"", "\"total\":\"2\"")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> mapper.map(sample.replace("127.0541", "14144000")))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void rejectsOpenRingsAndMalformedGeometry() {
    assertThatThrownBy(
            () -> mapper.map(sample.replace("[127.054,37.544]]]]", "[127.055,37.544]]]]")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> mapper.map(sample.replace("MultiPolygon", "Point")))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void neverIncludesProviderErrorText() {
    assertThatThrownBy(
            () ->
                mapper.map(
                    """
                    {"response":{"status":"ERROR","error":{"code":"INCORRECT_KEY","text":"secret-provider-url"}}}
                    """))
        .isInstanceOf(DomainException.class)
        .hasMessageNotContaining("secret-provider-url");
  }
}
