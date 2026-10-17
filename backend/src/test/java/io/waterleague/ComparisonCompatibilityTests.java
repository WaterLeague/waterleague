package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.comparison.exception.IncompatibleComparisonException;
import io.waterleague.comparison.service.ComparisonCompatibilityService;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class ComparisonCompatibilityTests {
  @Test
  void permitsDifferentRainButRejectsChangedPhysicsCostsAndMissingEvidence() throws Exception {
    var json = new ObjectMapper();
    ObjectNode source;
    try (var stream = new ClassPathResource("models/seongsu-lab.json").getInputStream()) {
      source = (ObjectNode) json.readTree(stream);
    }
    var service = new ComparisonCompatibilityService();
    var rain = source.deepCopy();
    rain.set("rainfall", json.createObjectNode().put("different", true));
    assertThatCode(() -> service.require(source, rain)).doesNotThrowAnyException();
    for (String field :
        new String[] {
          "hydrology",
          "cells",
          "generatorSha256",
          "engineRevision",
          "scoreRule",
          "unitCosts",
          "budget",
          "geometrySourceHash"
        }) {
      var changed = source.deepCopy();
      changed.put(field, "다른 입력");
      assertThatThrownBy(() -> service.require(source, changed))
          .isInstanceOf(IncompatibleComparisonException.class);
      var missing = source.deepCopy();
      missing.remove(field);
      assertThatThrownBy(() -> service.require(missing, missing))
          .isInstanceOf(IncompatibleComparisonException.class);
    }
  }
}
