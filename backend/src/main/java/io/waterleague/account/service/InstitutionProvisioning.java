package io.waterleague.account.service;

import io.waterleague.account.repository.AccountRepository;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("provision")
public class InstitutionProvisioning implements ApplicationRunner {
  private final AccountRepository accounts;
  private final InstitutionMfaService mfa;
  private final JdbcTemplate db;
  private final TransactionTemplate tx;

  public InstitutionProvisioning(
      AccountRepository a, InstitutionMfaService m, JdbcTemplate d, TransactionTemplate t) {
    accounts = a;
    mfa = m;
    db = d;
    tx = t;
  }

  public void run(ApplicationArguments args) {
    var console = System.console();
    if (console == null) throw new IllegalStateException("기관 승인은 로컬 대화형 터미널 필요");
    String name = console.readLine("승인할 기존 회원 아이디: ");
    var a = accounts.byUsername(name).orElseThrow(() -> new IllegalArgumentException("회원 없음"));
    String orgInput = console.readLine("기관 UUID (신규 기관은 빈 값): ");
    UUID org = orgInput.isBlank() ? UUID.randomUUID() : UUID.fromString(orgInput);
    String orgName =
        orgInput.isBlank()
            ? console.readLine("기관명: ")
            : db.queryForObject(
                "SELECT name FROM organizations WHERE id=? AND approved=true", String.class, org);
    if (orgName == null || orgName.isBlank() || orgName.length() > 100)
      throw new IllegalArgumentException("기관명 확인 필요");
    String confirmed = console.readLine("%s / %s 소속 확인 후 '승인' 입력: ", name, orgName);
    if (!"승인".equals(confirmed)) {
      System.exit(1);
      return;
    }
    String secret =
        tx.execute(
            status -> {
              db.queryForObject(
                  "SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, a.id());
              if (orgInput.isBlank())
                db.update(
                    "INSERT INTO organizations(id,name,approved) VALUES(?,?,true)",
                    org,
                    orgName.strip());
              String value = mfa.provision(a.id());
              db.update(
                  "UPDATE accounts SET role='INSTITUTION',organization_id=?,enabled=true WHERE"
                      + " id=?",
                  org,
                  a.id());
              db.update("DELETE FROM SPRING_SESSION WHERE PRINCIPAL_NAME=?", name);
              db.update(
                  "INSERT INTO audit_events(id,actor_id,action,object_id,created_at) VALUES(?,?,?,"
                      + " ?,CURRENT_TIMESTAMP)",
                  UUID.randomUUID(),
                  null,
                  "INSTITUTION_PROVISIONED",
                  a.id());
              return value;
            });
    // 인증 앱 등록 주소는 일반 로그·파일에 남기지 않고 운영자 터미널에만 표시한다.
    console.printf("기관 승인 완료. 인증 앱에 아래 주소의 비밀키 등록 후 안전한 경로로 본인 전달.\n");
    console.printf(
        "otpauth://totp/WaterLeague:%s?secret=%s&issuer=WaterLeague&algorithm=SHA1&digits=6&period=30%n",
        URLEncoder.encode(name, StandardCharsets.UTF_8), secret);
    System.exit(0);
  }
}
