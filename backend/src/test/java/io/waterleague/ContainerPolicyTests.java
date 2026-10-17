package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.security.ContainerPolicy;
import java.util.Base64;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class ContainerPolicyTests {
  MockEnvironment environment() {
    var e = new MockEnvironment();
    e.setActiveProfiles("container");
    e.setProperty("server.servlet.session.cookie.secure", "true");
    e.setProperty("server.servlet.session.cookie.name", "__Host-waterleague");
    e.setProperty("spring.flyway.enabled", "false");
    e.setProperty("spring.datasource.username", "wl_api");
    e.setProperty("spring.datasource.password", "test-only");
    e.setProperty("server.forward-headers-strategy", "framework");
    e.setProperty("waterleague.mfa-key", Base64.getEncoder().encodeToString(new byte[32]));
    return e;
  }

  @Test
  void acceptsSeparatedRuntimeConfiguration() {
    assertThatCode(() -> ContainerPolicy.validate(environment())).doesNotThrowAnyException();
  }

  @Test
  void rejectsInsecureOverridesWithoutRevealingValues() {
    Map.of(
            "server.servlet.session.cookie.secure", "false",
            "server.servlet.session.cookie.name", "local",
            "server.servlet.session.cookie.domain", "localhost",
            "spring.flyway.enabled", "true",
            "spring.datasource.username", "wl_owner",
            "spring.datasource.password", " ",
            "server.forward-headers-strategy", "none",
            "waterleague.mfa-key", "private-value!")
        .forEach((key, value) -> {
          var e = environment().withProperty(key, value);
          assertThatThrownBy(() -> ContainerPolicy.validate(e))
              .hasMessage("CONTAINER_CONFIGURATION_INVALID").hasNoCause();
        });
    for (String profile : new String[] {"local", "provision"}) {
      var e = environment();
      e.setActiveProfiles("container", profile);
      assertThatThrownBy(() -> ContainerPolicy.validate(e))
          .hasMessage("CONTAINER_CONFIGURATION_INVALID");
    }
    var e = environment().withProperty("waterleague.mfa-key", Base64.getEncoder().encodeToString(new byte[31]));
    assertThatThrownBy(() -> ContainerPolicy.validate(e)).hasMessage("CONTAINER_CONFIGURATION_INVALID");
  }
}
