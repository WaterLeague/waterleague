package io.waterleague.reference.entity;

import java.util.List;
import tools.jackson.databind.JsonNode;

public record ReferenceDocument(
    String hash, String source, String ledger, JsonNode report, List<String> modelHashes) {}
