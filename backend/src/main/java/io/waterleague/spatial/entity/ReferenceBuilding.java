package io.waterleague.spatial.entity;

import java.util.List;

public record ReferenceBuilding(
    String id, String name, Integer aboveGroundFloors, List<List<List<List<Double>>>> polygons) {}
