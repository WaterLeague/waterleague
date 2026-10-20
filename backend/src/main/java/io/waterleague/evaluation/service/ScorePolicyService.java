package io.waterleague.evaluation.service;

import io.waterleague.common.service.JsonService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class ScorePolicyService {
  private final JsonService json;
  private final String raw;
  private final String sha256;

  public ScorePolicyService(JsonService json) throws IOException {
    this.json = json;
    raw =
        new ClassPathResource("evaluation/game-score-policy-v1.json")
            .getContentAsString(StandardCharsets.UTF_8);
    var policy = json.tree(raw);
    if (!policy.path("version").asString().equals("ABSOLUTE_ACCOUNTED_VOLUME_RANKING_V1")
        || policy.path("weeklyDecimalPlaces").asInt() != 9
        || policy.path("submissionDecimalPlaces").asInt() != 18
        || !policy.path("tie").asString().equals("EXACT_STORED_DECIMAL_EQUALITY"))
      throw new IllegalStateException("평가 정책 불일치");
    sha256 = json.hash(raw);
  }

  public String sha256() {
    return sha256;
  }

  public JsonNode descriptor() {
    var policy = (tools.jackson.databind.node.ObjectNode) json.tree(raw);
    policy.remove("files");
    policy.put("sha256", sha256);
    return policy;
  }
}
