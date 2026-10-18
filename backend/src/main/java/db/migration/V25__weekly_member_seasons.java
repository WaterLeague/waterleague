package db.migration;

import java.sql.Timestamp;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.flywaydb.core.api.migration.*;

public class V25__weekly_member_seasons extends BaseJavaMigration {
  @Override
  public void migrate(Context context) throws Exception {
    var connection = context.getConnection();
    var names = new ArrayList<String>();
    try (var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT tc.constraint_name,cc.check_clause FROM"
                    + " information_schema.table_constraints tc JOIN"
                    + " information_schema.check_constraints cc ON"
                    + " cc.constraint_catalog=tc.constraint_catalog AND"
                    + " cc.constraint_schema=tc.constraint_schema AND"
                    + " cc.constraint_name=tc.constraint_name WHERE"
                    + " tc.table_schema=current_schema() AND"
                    + " LOWER(tc.table_name)='shared_installations' AND"
                    + " tc.constraint_type='CHECK'")) {
      while (rows.next())
        if (rows.getString(2).toLowerCase(Locale.ROOT).contains("occupied_site"))
          names.add(rows.getString(1));
    }
    try (var statement = connection.createStatement()) {
      for (var name : names) {
        if (!name.matches("[A-Za-z0-9_]+")) throw new IllegalStateException("설치 제약 이름 오류");
        statement.execute("ALTER TABLE shared_installations DROP CONSTRAINT \"" + name + "\"");
      }
      statement.execute(
          "ALTER TABLE shared_installations ALTER COLUMN occupied_site TYPE VARCHAR(128)");
      statement.execute(
          "ALTER TABLE shared_installations ADD COLUMN season_ends_at TIMESTAMP WITH TIME ZONE");
      // 과거 입력·점수는 유지하고 현재 배치만 전환 주의 종료 시각에 고정한다.
      statement.execute(
          "UPDATE shared_installations SET occupied_site=CAST(owner_id AS VARCHAR) || ':' ||"
              + " district_id || ':' || cell_id WHERE removed_at IS NULL");
      statement.execute(
          "ALTER TABLE shared_installations ADD CONSTRAINT shared_member_site CHECK((removed_at IS"
              + " NULL AND (occupied_site=CAST(owner_id AS VARCHAR) || ':' || district_id || ':' ||"
              + " cell_id OR (season_ends_at IS NULL AND occupied_site=district_id || ':' ||"
              + " cell_id)) AND occupied_site IS NOT NULL) OR (removed_at IS NOT NULL AND"
              + " occupied_site IS NULL))");
      statement.execute(
          "CREATE INDEX shared_season_expiry ON shared_installations(season_ends_at,owner_id)");
      statement.execute(
          "ALTER TABLE shared_installations ADD CONSTRAINT shared_season_period"
              + " CHECK(season_ends_at IS NULL OR season_ends_at>installed_at)");
    }
    Instant now;
    try (var statement = connection.createStatement();
        var rows = statement.executeQuery("SELECT CURRENT_TIMESTAMP")) {
      rows.next();
      now = rows.getTimestamp(1).toInstant();
    }
    var end =
        now.atZone(ZoneId.of("Asia/Seoul"))
            .toLocalDate()
            .with(TemporalAdjusters.next(DayOfWeek.MONDAY))
            .atStartOfDay(ZoneId.of("Asia/Seoul"))
            .toInstant();
    try (var statement =
        connection.prepareStatement(
            "UPDATE shared_installations SET season_ends_at=? WHERE removed_at IS NULL AND"
                + " installed_at<?")) {
      statement.setTimestamp(1, Timestamp.from(end));
      statement.setTimestamp(2, Timestamp.from(end));
      statement.executeUpdate();
    }
  }
}
