package io.waterleague.reference.mapper;

import io.waterleague.reference.view.ReferenceView;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

@Component
public class ReferenceMapper {
  public ReferenceView view(String hash, JsonNode report) {
    return new ReferenceView(hash, report);
  }
}
