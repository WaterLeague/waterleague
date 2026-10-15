package io.waterleague.comparison.service;

import io.waterleague.comparison.exception.IncompatibleComparisonException;
import java.util.List;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class ComparisonCompatibilityService {
  private static final List<String> FIXED_FIELDS =
      List.of(
          "cells",
          "unitCosts",
          "costModel",
          "currency",
          "budget",
          "maxPlacements",
          "hydrology",
          "generatorSha256",
          "engineRevision",
          "engine",
          "scoreRule",
          "geometrySourceHash");

  public void require(JsonNode source, JsonNode target) {
    for (var field : FIXED_FIELDS)
      if (!source.hasNonNull(field)
          || !target.hasNonNull(field)
          || !source.path(field).equals(target.path(field)))
        throw new IncompatibleComparisonException();
  }
}
