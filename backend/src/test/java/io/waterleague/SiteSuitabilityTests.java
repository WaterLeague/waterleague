package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.installation.entity.SiteSuitability;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.view.SiteView;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class SiteSuitabilityTests {
  private final ObjectMapper json = new ObjectMapper();

  @Test
  void sharedBoundaryCasesKeepUnknownConditionsAndBlockRestrictions() throws Exception {
    var fixture =
        json.readTree(
            Files.readString(Path.of("../simulation/tests/fixtures/site-suitability-v1.json")));
    var output = new TreeMap<String, SiteSuitability>();
    for (var example : fixture.path("cases")) {
      var result = SiteSuitability.assess(example.path("cell"));
      assertThat(result.status()).isEqualTo(example.path("expected").asString());
      assertThat(result.constructionApproved()).isFalse();
      assertThat(result.explorationAllowed())
          .isEqualTo(Set.of("UNKNOWN", "ELIGIBLE").contains(result.status()));
      var site = mock(SiteView.class);
      when(site.suitability()).thenReturn(result);
      var repository = mock(SiteCatalogRepository.class, CALLS_REAL_METHODS);
      doReturn(site).when(repository).require("11110", "TEST_ONLY");
      if (result.explorationAllowed()) {
        assertThat(repository.requireInstallable("11110", "TEST_ONLY")).isSameAs(site);
      } else {
        assertThatThrownBy(() -> repository.requireInstallable("11110", "TEST_ONLY"))
            .isInstanceOfSatisfying(
                DomainException.class,
                error -> assertThat(error.code()).isEqualTo(ErrorCode.SITE_SUITABILITY_RESTRICTED));
      }
      output.put(example.path("id").asString(), result);
    }
    Path target = Path.of("../tmp/site-suitability-java-v1.json");
    Files.createDirectories(target.getParent());
    Files.writeString(target, json.writeValueAsString(output));
  }

  @Test
  void malformedAndUnsourcedConditionsCannotBecomeEligible() {
    for (String payload :
        List.of(
            "{\"kind\":\"ROOF\",\"siteEligibility\":null}",
            "{\"kind\":\"ROOF\",\"siteEligibility\":\"SAFE\"}",
            "{\"kind\":\"ROOF\",\"siteConditions\":null}",
            "{\"kind\":\"ROOF\",\"siteConditions\":{\"SOIL\":{}}}",
            "{\"kind\":\"ROOF\",\"siteConditions\":{\"DRAINAGE\":null}}",
            "{\"kind\":\"ROOF\",\"siteConditions\":{\"DRAINAGE\":{\"status\":\"ELIGIBLE\",\"reason\":\"시험\",\"evidence\":null}}}")) {
      assertThatThrownBy(() -> SiteSuitability.assess(json.readTree(payload)))
          .isInstanceOfSatisfying(
              DomainException.class,
              error -> assertThat(error.code()).isEqualTo(ErrorCode.SPATIAL_DATA_INVALID));
    }
    var cell = (ObjectNode) json.readTree("""
        {"kind":"ROOF","siteConditions":{"DRAINAGE":{"status":"ELIGIBLE","reason":"시험",
        "evidence":{"title":"시험","url":"https://example.org","reference":"시험",
        "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}}
        """);
    for (String url : List.of("http://example.org", "file:///etc/passwd", "https://user:secret@example.org", "https://example.org/\n")) {
      ((ObjectNode) cell.path("siteConditions").path("DRAINAGE").path("evidence")).put("url", url);
      assertThatThrownBy(() -> SiteSuitability.assess(cell)).isInstanceOf(DomainException.class);
    }
  }
}
