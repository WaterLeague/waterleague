package io.waterleague.installation.entity;

public enum SiteSurface {
  ROADWAY,
  WALKWAY,
  OTHER;

  public boolean matches(io.waterleague.installation.view.SiteView site) {
    var placement = site.physicalInputs().path("streetPlacement");
    if (this == OTHER) return placement.isMissingNode();
    var role = placement.path("role").asString();
    return this == ROADWAY
        ? role.equals("ROADWAY")
        : role.equals("SIDEWALK") || role.equals("WALKWAY");
  }
}
