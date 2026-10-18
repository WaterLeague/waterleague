package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.installation.dto.CisternLayoutRequest;
import io.waterleague.installation.exception.CisternPlanException;
import io.waterleague.installation.service.CisternLayoutService;
import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class CisternLayoutTests {
  record Example(
      String name,
      List<List<Double>> ring,
      List<Double> center,
      double area,
      double depth,
      CisternLayoutRequest layout,
      boolean contained,
      List<List<Double>> expected) {}

  @Test
  void fullBoundaryIncludingConcavityWallsRotationAndTranslation() throws Exception {
    var mapper = JsonMapper.builder().build();
    try (var source = getClass().getResourceAsStream("/cistern-layout-cases.json")) {
      for (var example : mapper.readValue(source, Example[].class)) {
        for (double offset : new double[] {0, 203000}) {
          var ring =
              example.ring().stream()
                  .map(p -> List.of(p.get(0) + offset, p.get(1) + offset))
                  .toList();
          var center = List.of(example.center().get(0) + offset, example.center().get(1) + offset);
          if (!example.contained()) {
            assertThatThrownBy(
                    () ->
                        CisternLayoutService.build(
                            ring,
                            center,
                            "a".repeat(64),
                            example.area(),
                            example.depth(),
                            example.layout()))
                .as(example.name())
                .isInstanceOf(CisternPlanException.class);
            continue;
          }
          var geometry =
              CisternLayoutService.build(
                  ring, center, "a".repeat(64), example.area(), example.depth(), example.layout());
          assertThat(geometry.contained()).as(example.name()).isTrue();
          assertThat(geometry.internalWidthM() * geometry.internalLengthM())
              .isCloseTo(example.area(), within(1e-8));
          if (example.expected() != null)
            for (int i = 0; i < 5; i++)
              for (int j = 0; j < 2; j++)
                assertThat(geometry.coordinates().get(i).get(j) - offset)
                    .isCloseTo(example.expected().get(i).get(j), within(1e-8));
          var reversed = new ArrayList<>(ring);
          Collections.reverse(reversed);
          assertThat(
                  CisternLayoutService.build(
                      reversed,
                      center,
                      "a".repeat(64),
                      example.area(),
                      example.depth(),
                      example.layout()))
              .isEqualTo(geometry);
        }
      }
    }
  }
}
