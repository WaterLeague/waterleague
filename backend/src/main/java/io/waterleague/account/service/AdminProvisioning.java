package io.waterleague.account.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("provision")
public class AdminProvisioning implements ApplicationRunner {
  private final AccountRepository accounts;
  private final InstitutionMfaService mfa;
  private final JdbcTemplate db;
  private final TransactionTemplate tx;
  private final PasswordEncoder passwords;

  public AdminProvisioning(
      AccountRepository a,
      InstitutionMfaService m,
      JdbcTemplate d,
      TransactionTemplate t,
      PasswordEncoder p) {
    accounts = a;
    mfa = m;
    db = d;
    tx = t;
    passwords = p;
  }

  public void run(ApplicationArguments args) {
    var console = System.console();
    if (console == null) throw new IllegalStateException("관리자 초기화는 로컬 대화형 터미널 필요");
    if (db.queryForObject("SELECT COUNT(*) FROM accounts WHERE role='ADMIN'", Integer.class) > 0)
      throw new IllegalStateException("관리자 계정이 이미 존재함");
    String name = console.readLine("단일 관리자 아이디: ");
    if (name == null || !name.matches("[a-z0-9_]{4,32}") || accounts.byUsername(name).isPresent())
      throw new IllegalArgumentException("새 관리자 아이디 확인 필요");
    char[] password = console.readPassword("관리자 비밀번호 (8~128자): ");
    if (password == null || password.length < 8 || password.length > 128)
      throw new IllegalArgumentException("비밀번호 길이 확인 필요");
    String encoded;
    try {
      encoded = passwords.encode(new String(password));
    } finally {
      Arrays.fill(password, '\0');
    }
    if (!"생성".equals(console.readLine("단일 관리자 생성 확인 ('생성' 입력): "))) {
      System.exit(1);
      return;
    }
    UUID id = UUID.randomUUID();
    String secret =
        tx.execute(
            status -> {
              accounts.add(
                  new Account(
                      id, name, "관리자", encoded, "ADMIN", null, "APPROVED", null, "", "", true));
              var value = mfa.provision(id);
              db.update(
                  "INSERT INTO audit_events(id,actor_id,action,object_id,created_at)"
                      + " VALUES(?,?,'ADMIN_BOOTSTRAPPED',?,CURRENT_TIMESTAMP)",
                  UUID.randomUUID(),
                  id,
                  id);
              return value;
            });
    // 관리자 본인의 인증 앱 등록 정보만 로컬 콘솔에 한 번 표시한다.
    console.printf("관리자 생성 완료. 인증 앱에 등록 후 화면 기록 제거.\n");
    console.printf(
        "otpauth://totp/WaterLeague:%s?secret=%s&issuer=WaterLeague&algorithm=SHA1&digits=6&period=30%n",
        URLEncoder.encode(name, StandardCharsets.UTF_8), secret);
    System.exit(0);
  }
}
