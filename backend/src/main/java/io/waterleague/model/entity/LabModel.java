package io.waterleague.model.entity;

import tools.jackson.databind.JsonNode;

public record LabModel(String hash, String source, JsonNode model) {}
