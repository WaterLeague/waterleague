package io.waterleague.installation.view;

import java.util.*;

public record SitePageView(
    List<SiteView> sites,
    Map<String, Integer> districtCounts,
    int matchedCount,
    int offset,
    int limit) {}
