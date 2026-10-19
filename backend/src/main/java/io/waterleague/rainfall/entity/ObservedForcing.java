package io.waterleague.rainfall.entity;

import tools.jackson.databind.JsonNode;

public record ObservedForcing(String hash, String source, JsonNode model) {
  public ObservedForcing { model = model.deepCopy(); }
  @Override public JsonNode model() { return model.deepCopy(); }
}
