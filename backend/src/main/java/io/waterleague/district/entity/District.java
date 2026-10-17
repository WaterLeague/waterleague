package io.waterleague.district.entity;

import java.util.List;

public record District(
    String id,
    String name,
    String mapId,
    String modelHash,
    List<Double> center,
    String stationId,
    String stationName) {}
