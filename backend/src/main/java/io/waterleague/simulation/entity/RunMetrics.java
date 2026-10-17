package io.waterleague.simulation.entity;

public record RunMetrics(
    double runoffM3,
    double peakM3s,
    double finalStorageM3,
    double runoffContinuityPercent,
    Double routingContinuityPercent,
    boolean routed) {}
