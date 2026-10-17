package io.waterleague.disaster.view;

import java.util.List;

public record DisasterView(List<Event> events) {
  public record Event(
      String id,
      String title,
      String eventDate,
      String summary,
      String evidenceTitle,
      String evidenceUrl,
      List<Region> regions) {}

  public record Region(
      String districtId,
      String modelHash,
      String stationName,
      String stationId,
      double distanceKm,
      String start,
      String end,
      double totalDepthMm,
      List<Double> depthsMm) {}
}
