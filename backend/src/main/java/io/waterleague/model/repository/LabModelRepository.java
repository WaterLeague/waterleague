package io.waterleague.model.repository;

import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class LabModelRepository {
  private final String hash;
  private final JsonNode model;

  public LabModelRepository(JsonService json) throws java.io.IOException {
    String text =
        new ClassPathResource("models/seongsu-lab.json").getContentAsString(StandardCharsets.UTF_8);
    model = json.tree(text);
    hash = json.hash(text);
  }

  public String hash() {
    return hash;
  }

  public JsonNode model() {
    return model;
  }
}
