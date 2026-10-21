package io.waterleague.notification.service;

import io.waterleague.common.service.JsonService;
import io.waterleague.notification.repository.NotificationRepository;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnWebApplication
public class DiscordNotifications {
  private final NotificationRepository outbox;
  private final JsonService json;
  private final URI endpoint;
  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(5))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();
  private long pausedUntil;

  public DiscordNotifications(
      NotificationRepository outbox,
      JsonService json,
      @Value("${waterleague.discord-webhook-url:}") String url) {
    this.outbox = outbox;
    this.json = json;
    endpoint = endpoint(url);
  }

  public static URI endpoint(String url) {
    if (url.isBlank()) return null;
    if (!url.matches(
        "https://discord\\.com/api/(?:v10/)?webhooks/[0-9]{10,25}/[A-Za-z0-9_-]{40,200}"))
      throw new IllegalStateException("DISCORD_WEBHOOK_CONFIGURATION_INVALID");
    return URI.create(url + "?wait=true");
  }

  public String message(NotificationRepository.Delivery delivery) {
    String title =
        switch (delivery.type()) {
          case "MEMBER_REGISTERED" -> "신규 회원 가입";
          case "WEEKLY_INSTALLED" -> "주간 서울 대항전 신규 설치";
          case "DISASTER_SUBMITTED" -> "재해 모드 제출 접수";
          default -> throw new IllegalStateException("NOTIFICATION_TYPE_INVALID");
        };
    var payload = json.tree(delivery.payload());
    var fields = new ArrayList<Map<String, Object>>();
    for (var field :
        List.of(
            "username",
            "displayName",
            "userId",
            "memberType",
            "districtId",
            "approvalStatus",
            "facilityType",
            "areaM2",
            "installedAt",
            "eventId")) {
      var value = payload.path(field);
      if (value.isMissingNode() || value.isNull()) continue;
      String text = value.asString();
      if (!text.isBlank())
        fields.add(
            Map.of(
                "name",
                label(field),
                "value",
                text.substring(0, Math.min(512, text.length())),
                "inline",
                true));
    }
    return json.write(
        Map.of(
            "allowed_mentions",
            Map.of("parse", List.of()),
            "embeds",
            List.of(
                Map.of(
                    "title",
                    title,
                    "fields",
                    fields,
                    "footer",
                    Map.of("text", "기록 ID: " + delivery.source())))));
  }

  private String label(String field) {
    return switch (field) {
      case "username" -> "아이디";
      case "displayName" -> "닉네임";
      case "userId" -> "회원 ID";
      case "memberType" -> "회원 유형";
      case "districtId" -> "소속·설치 구 코드";
      case "approvalStatus" -> "승인 상태";
      case "facilityType" -> "시설 종류";
      case "areaM2" -> "면적 (m²)";
      case "installedAt" -> "설치 시각";
      case "eventId" -> "재해 사건";
      default -> field;
    };
  }

  @Scheduled(fixedDelay = 1000, initialDelay = 15000)
  public void sendNext() {
    if (endpoint == null || System.currentTimeMillis() < pausedUntil) return;
    outbox
        .claim()
        .ifPresent(
            delivery -> {
              long delay = Math.min(3600, 30L << (delivery.attempts() - 1));
              try {
                var request =
                    HttpRequest.newBuilder(endpoint)
                        .timeout(Duration.ofSeconds(10))
                        .header("Content-Type", "application/json")
                        .header("User-Agent", "WaterLeague/1.0")
                        .POST(HttpRequest.BodyPublishers.ofString(message(delivery)))
                        .build();
                var response = client.send(request, HttpResponse.BodyHandlers.discarding());
                int status = response.statusCode();
                if (status == 429) {
                  delay = retryAfter(response.headers().firstValue("Retry-After").orElse("60"));
                  pausedUntil = System.currentTimeMillis() + delay * 1000;
                }
                outbox.finish(
                    delivery,
                    status >= 200 && status < 300,
                    status >= 300 && status < 500 && status != 408 && status != 429,
                    delay,
                    "HTTP_" + status);
              } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                outbox.finish(delivery, false, false, delay, "INTERRUPTED");
              } catch (Exception unavailable) {
                // HTTP 예외에 포함될 수 있는 웹훅 토큰·사용자 정보는 로그에 남기지 않는다.
                outbox.finish(delivery, false, false, delay, "DELIVERY_UNAVAILABLE");
              }
            });
  }

  public static long retryAfter(String value) {
    try {
      double seconds = Double.parseDouble(value);
      return Double.isFinite(seconds) && seconds >= 0
          ? (long) Math.ceil(Math.min(31536000, Math.max(1, seconds)))
          : 60;
    } catch (NumberFormatException invalid) {
      return 60;
    }
  }

  @Scheduled(fixedDelay = 3600000, initialDelay = 60000)
  public void cleanup() {
    outbox.cleanup();
  }
}
