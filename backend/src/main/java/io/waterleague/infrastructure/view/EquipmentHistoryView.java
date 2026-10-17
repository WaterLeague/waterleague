package io.waterleague.infrastructure.view;

import io.waterleague.infrastructure.entity.EquipmentHistory;
import java.util.List;
import tools.jackson.databind.JsonNode;

public record EquipmentHistoryView(
    String version, String sha256, String usage, JsonNode source,
    String eventId, String eventDate, List<Entry> records) {
  public record Entry(EquipmentHistory record, String temporalStatus,
                      boolean sourcePrecedesEvent, boolean simulationIncluded) {}
}
