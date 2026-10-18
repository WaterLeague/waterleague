package io.waterleague.infrastructure.view;

import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;

public record InfrastructureView(
    String version,
    String sha256,
    String usage,
    List<JsonNode> sources,
    Map<String, Long> statusCounts,
    List<Asset> assets) {
  public record Asset(
      String id,
      String sourceId,
      String name,
      String kind,
      List<Double> center,
      String districtId,
      String geometryEvidence,
      String verticalLayer,
      String validFrom,
      String validTo,
      String operationStatus,
      String hydraulicStatus,
      JsonNode pumpSpecs,
      JsonNode footprint) {}
}
