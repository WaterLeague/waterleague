package io.waterleague.common.security;

import java.util.Base64;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@Profile("container & !migrate")
public class ContainerPolicy {
  public ContainerPolicy(Environment environment) {
    validate(environment);
  }

  public static void validate(Environment e) {
    try {
      if (e.matchesProfiles("local", "provision")
          || !"true".equals(e.getProperty("server.servlet.session.cookie.secure"))
          || !"__Host-waterleague".equals(e.getProperty("server.servlet.session.cookie.name"))
          || e.getProperty("server.servlet.session.cookie.domain") != null
          || !"false".equals(e.getProperty("spring.flyway.enabled"))
          || !"wl_api".equals(e.getProperty("spring.datasource.username"))
          || e.getProperty("spring.datasource.password", "").isBlank()
          || !"framework".equals(e.getProperty("server.forward-headers-strategy"))
          || Base64.getDecoder().decode(e.getProperty("waterleague.mfa-key", "")).length != 32)
        throw new IllegalArgumentException();
    } catch (IllegalArgumentException error) {
      throw new IllegalStateException("CONTAINER_CONFIGURATION_INVALID");
    }
  }
}
