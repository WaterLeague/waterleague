package io.waterleague.infrastructure.entity;

public record EquipmentHistory(
    String id, String assetId, int sourceRow, String name, String address,
    int installedYear, Integer expandedYear, String referenceDate,
    String motorSizeRaw, int motorCount, String engineSizeRaw, int engineCount,
    String sizeUnitRaw, String linkBasis) {}
