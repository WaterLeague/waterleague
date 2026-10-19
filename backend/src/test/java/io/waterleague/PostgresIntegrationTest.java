package io.waterleague;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class PostgresIntegrationTest {
  @BeforeAll
  static void clearPreviousScenario(@Autowired JdbcTemplate database, TestInfo test) {
    if (Boolean.getBoolean("waterleague.integration.preserve-fixtures")
        || test.getTestClass().orElseThrow() == HistoricalDesignRestartTests.class) return;
    // 시험 클래스가 남긴 대기 작업·세션이 다음 클래스의 상한 검사를 오염시키지 않게 한다.
    database.execute("TRUNCATE accounts, organizations, spring_session, rate_limits CASCADE");
  }

  @DynamicPropertySource
  static void postgresDatabase(DynamicPropertyRegistry registry) {
    String url = System.getProperty("waterleague.integration.jdbc");
    // 실제 PostgreSQL의 제약·부분 인덱스를 검사하고 개발 DB 접속은 거부한다.
    if (url == null
        || !url.matches(
            "jdbc:postgresql://(?:127\\.0\\.0\\.1|localhost|\\[::1\\]):[0-9]+/waterleague_(?:test|[a-z_]+_test_[a-f0-9]{32})"))
      throw new IllegalStateException(
          "격리 PostgreSQL 필요: scripts/verify_league_postgres.py --suite backend");
    registry.add("spring.datasource.url", () -> url);
    registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    registry.add("spring.datasource.username", () -> System.getenv("WL_INTEGRATION_USER"));
    registry.add("spring.datasource.password", () -> System.getenv("WL_INTEGRATION_PASSWORD"));
  }
}
