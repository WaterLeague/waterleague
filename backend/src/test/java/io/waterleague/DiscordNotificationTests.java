package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.notification.repository.NotificationRepository;
import io.waterleague.notification.service.DiscordNotifications;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class DiscordNotificationTests {
  @Test
  void rejectsAlternativeHostsQueriesAndRedirectTargetsWithoutExposingToken() {
    String token = "a".repeat(60);
    assertThat(DiscordNotifications.endpoint("")).isNull();
    assertThat(
            DiscordNotifications.endpoint(
                    "https://discord.com/api/webhooks/123456789012345678/" + token)
                .getQuery())
        .isEqualTo("wait=true");
    for (String url :
        new String[] {
          "http://discord.com/api/webhooks/123456789012345678/" + token,
          "https://discord.com.attacker.invalid/api/webhooks/123456789012345678/" + token,
          "https://discord.com/api/webhooks/123456789012345678/" + token + "?thread_id=1",
          "https://127.0.0.1/api/webhooks/123456789012345678/" + token
        }) {
      assertThatThrownBy(() -> DiscordNotifications.endpoint(url))
          .hasMessage("DISCORD_WEBHOOK_CONFIGURATION_INVALID");
    }
  }

  @Test
  void limitsRateRetryAndSuppressesAllMentionsAndUnlistedFields() {
    assertThat(DiscordNotifications.retryAfter("1.25")).isEqualTo(2);
    assertThat(DiscordNotifications.retryAfter("NaN")).isEqualTo(60);
    assertThat(DiscordNotifications.retryAfter("Infinity")).isEqualTo(60);
    assertThat(DiscordNotifications.retryAfter("-2")).isEqualTo(60);
    var json = new JsonService(JsonMapper.builder().build());
    var sender = new DiscordNotifications(null, json, "");
    var message =
        json.tree(
            sender.message(
                new NotificationRepository.Delivery(
                    UUID.randomUUID(),
                    "WEEKLY_INSTALLED",
                    UUID.randomUUID(),
                    "{\"username\":\"player\",\"displayName\":\"@everyone\",\"areaM2\":25,\"password\":\"never-send\"}",
                    1,
                    UUID.randomUUID())));
    assertThat(message.path("allowed_mentions").path("parse").size()).isZero();
    assertThat(message.toString()).contains("신규 설치", "25").doesNotContain("never-send", "password");
  }
}
