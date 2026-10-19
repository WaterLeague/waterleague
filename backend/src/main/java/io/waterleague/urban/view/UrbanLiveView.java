package io.waterleague.urban.view;

import java.time.Instant;
import java.util.List;

public record UrbanLiveView(String catalogSha256, String sourceUrl, List<Place> places) {
  public record Population(
      long minimum,
      long maximum,
      int sourceHourKst,
      String congestion,
      Instant retrievedAt,
      Instant validUntil,
      String sourceSha256) {}

  public record Traffic(
      double speedKmh,
      Instant observedAt,
      Instant retrievedAt,
      Instant validUntil,
      String sourceSha256) {}

  public record Place(
      String id,
      String name,
      Population population,
      Traffic traffic,
      String populationStatus,
      String trafficStatus) {}
}
