package io.waterleague.reference.view;

import tools.jackson.databind.JsonNode;

public record ReferenceView(String reportHash, JsonNode report) {}
