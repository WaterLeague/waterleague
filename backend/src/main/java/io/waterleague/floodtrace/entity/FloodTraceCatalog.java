package io.waterleague.floodtrace.entity;

import java.util.List;
import java.util.Map;

public record FloodTraceCatalog(
    String version, String usage, String projection, List<Double> originM,
    double displayRoundingM, int tileSizeM, String sourceUrl, String publisher, String license,
    List<Event> events) {
  public record Event(
      String id, String title, int year, String periodStart, String periodEnd,
      String sourceSha256, String fileModifiedAt, int recordCount, int includedCount,
      Map<String, Integer> statusCounts, double unionAreaM2, List<Tile> tiles) {}

  public record Tile(String id, List<Double> bounds, String sha256, int bytes) {}
}
