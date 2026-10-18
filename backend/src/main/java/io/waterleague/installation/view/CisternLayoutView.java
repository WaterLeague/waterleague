package io.waterleague.installation.view;

import java.util.List;

public record CisternLayoutView(
    String method,
    String sourceModelHash,
    List<Double> center,
    double internalWidthM,
    double internalLengthM,
    double wallThicknessM,
    double outerWidthM,
    double outerLengthM,
    double storageDepthM,
    double rotationDeg,
    List<List<Double>> coordinates,
    boolean contained) {}
