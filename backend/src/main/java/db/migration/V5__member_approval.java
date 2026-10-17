package db.migration;

import java.util.ArrayList;
import java.util.Locale;
import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

public class V5__member_approval extends BaseJavaMigration {
  @Override
  public void migrate(Context context) throws Exception {
    var connection = context.getConnection();
    var names = new ArrayList<String>();
    // 기존 자동 생성 제약명은 PostgreSQL과 시험 DB에서 다르므로 메타데이터로 찾는다.
    try (var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT tc.constraint_name,cc.check_clause FROM"
                    + " information_schema.table_constraints tc JOIN"
                    + " information_schema.check_constraints cc ON"
                    + " cc.constraint_catalog=tc.constraint_catalog AND"
                    + " cc.constraint_schema=tc.constraint_schema AND"
                    + " cc.constraint_name=tc.constraint_name WHERE tc.table_name='accounts' AND"
                    + " tc.constraint_type='CHECK'")) {
      while (rows.next())
        if (rows.getString(2).toLowerCase(Locale.ROOT).contains("role"))
          names.add(rows.getString(1));
    }
    try (var statement = connection.createStatement()) {
      for (String name : names) {
        if (!name.matches("[A-Za-z0-9_]+")) throw new IllegalStateException("계정 제약 이름 확인 필요");
        statement.execute("ALTER TABLE accounts DROP CONSTRAINT \"" + name + "\"");
      }
      for (String sql :
          new String[] {
            "ALTER TABLE accounts ADD COLUMN member_type VARCHAR(20)",
            "ALTER TABLE accounts ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT"
                + " 'PENDING'",
            "ALTER TABLE accounts ADD COLUMN requested_organization_name VARCHAR(100) NOT NULL"
                + " DEFAULT ''",
            "ALTER TABLE accounts ADD COLUMN application_purpose VARCHAR(2000) NOT NULL DEFAULT ''",
            "ALTER TABLE accounts ADD COLUMN admin_slot INT UNIQUE",
            "UPDATE accounts SET member_type=role,approval_status=CASE WHEN role='PLAYER' THEN"
                + " 'APPROVED' ELSE 'PENDING' END",
            "UPDATE accounts SET requested_organization_name=COALESCE((SELECT name FROM"
                + " organizations o WHERE o.id=accounts.organization_id),'')",
            "UPDATE accounts SET role='MEMBER'",
            "ALTER TABLE accounts ADD CONSTRAINT account_role CHECK(role IN ('MEMBER','ADMIN'))",
            "ALTER TABLE accounts ADD CONSTRAINT account_approval CHECK(approval_status IN"
                + " ('PENDING','APPROVED','REJECTED','SUSPENDED'))",
            "ALTER TABLE accounts ADD CONSTRAINT account_single_admin CHECK((role='ADMIN' AND"
                + " admin_slot IS NOT NULL AND admin_slot=1 AND member_type IS NULL AND"
                + " organization_id IS NULL) OR (role='MEMBER' AND admin_slot IS NULL AND"
                + " member_type IS NOT NULL AND member_type IN"
                + " ('PLAYER','BUSINESS','INSTITUTION','GOVERNMENT')))",
            "ALTER TABLE accounts ADD CONSTRAINT account_organization CHECK((member_type='PLAYER'"
                + " AND organization_id IS NULL) OR member_type IS NULL OR (member_type IN"
                + " ('BUSINESS','INSTITUTION','GOVERNMENT') AND (approval_status<>'APPROVED' OR"
                + " organization_id IS NOT NULL)))",
            "ALTER TABLE account_mfa ADD COLUMN confirmed BOOLEAN NOT NULL DEFAULT TRUE",
            "CREATE TABLE account_reviews(id UUID PRIMARY KEY, account_id UUID NOT NULL REFERENCES"
                + " accounts(id), reviewer_id UUID NOT NULL REFERENCES accounts(id), decision"
                + " VARCHAR(20) NOT NULL, reason VARCHAR(1000) NOT NULL, organization_id UUID"
                + " REFERENCES organizations(id), created_at TIMESTAMP WITH TIME ZONE NOT NULL)",
            "CREATE INDEX account_reviews_account ON account_reviews(account_id,created_at)",
            "DELETE FROM SPRING_SESSION"
          }) statement.execute(sql);
    }
  }
}
