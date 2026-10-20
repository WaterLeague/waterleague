package io.waterleague.installation.view;

import java.util.List;

public record CisternEquipmentView(
    String method,
    String sourceModelHash,
    String specificationId,
    String catalogSha256,
    List<Double> center,
    double widthM,
    double lengthM,
    double heightM,
    double rotationDeg,
    List<List<Double>> coordinates,
    boolean contained) {}
