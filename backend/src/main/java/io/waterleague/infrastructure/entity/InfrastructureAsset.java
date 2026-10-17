package io.waterleague.infrastructure.entity;

import java.util.List;
import tools.jackson.databind.JsonNode;

public record InfrastructureAsset(
    String id, String sourceId, String name, String kind, List<Double> center,
    String districtId, String displayStatus, String geometryEvidence,
    String verticalLayer, String validFrom, String validTo, String operationStatus,
    String hydraulicStatus, JsonNode sourceProperties, JsonNode pumpSpecs) {}
