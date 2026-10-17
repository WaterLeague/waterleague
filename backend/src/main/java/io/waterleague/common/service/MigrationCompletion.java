package io.waterleague.common.service;

import org.flywaydb.core.Flyway;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("migrate")
public class MigrationCompletion implements ApplicationRunner {
  private final ConfigurableApplicationContext context;
  private final Flyway flyway;

  public MigrationCompletion(ConfigurableApplicationContext context, Flyway flyway) {
    this.context = context;
    this.flyway = flyway;
  }

  @Override
  public void run(ApplicationArguments args) {
    flyway.validate();
    if (flyway.info().pending().length != 0)
      throw new IllegalStateException("MIGRATION_INCOMPLETE");
    context.close();
  }
}
