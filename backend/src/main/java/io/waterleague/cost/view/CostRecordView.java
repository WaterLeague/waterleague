package io.waterleague.cost.view;

import tools.jackson.databind.JsonNode;

public record CostRecordView(String status, String sha256, JsonNode estimate) {}
