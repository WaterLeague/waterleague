package io.waterleague.installation.view;

import java.math.BigDecimal;
import java.util.*;

public record SiteView(
    String districtId,
    String cellId,
    String name,
    String kind,
    List<List<Double>> coordinates,
    List<Double> center,
    double heightM,
    double areaM2,
    BigDecimal maxAreaM2,
    List<String> allowedTypes,
    Map<String, BigDecimal> unitCosts,
    BigDecimal budget,
    String modelHash,
    List<String> sourceIds) {}
