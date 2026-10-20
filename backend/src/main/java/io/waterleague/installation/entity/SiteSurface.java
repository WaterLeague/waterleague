package io.waterleague.installation.entity;

public enum SiteSurface {
  ROADWAY,
  WALKWAY,
  PARKING,
  OTHER;

  public String nativeRole() {
    return switch (this) {
      case ROADWAY -> "ROAD_AREA";
      case WALKWAY -> "SIDEWALK_AREA";
      case PARKING -> "PARKING_AREA";
      case OTHER -> "OTHER";
    };
  }

  public boolean matches(io.waterleague.installation.view.SiteView site) {
    return this == OTHER
        ? !java.util.Set.of("ROAD_AREA", "SIDEWALK_AREA", "PARKING_AREA").contains(site.sourceRole())
        : nativeRole().equals(site.sourceRole());
  }
}
