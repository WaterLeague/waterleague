package io.waterleague.installation.view;

import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public record CisternPlanView(UUID id, String inputHash, Instant createdAt, JsonNode snapshot) {}
