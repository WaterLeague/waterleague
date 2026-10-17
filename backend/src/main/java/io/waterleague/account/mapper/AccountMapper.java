package io.waterleague.account.mapper;

import io.waterleague.account.entity.Account;
import io.waterleague.account.view.AccountView;

public final class AccountMapper {
  private AccountMapper() {}

  public static AccountView view(Account a) {
    return new AccountView(
        a.id(),
        a.username(),
        a.displayName(),
        a.role(),
        a.memberType(),
        a.approvalStatus(),
        a.organizationId(),
        a.districtId(),
        a.affiliationType());
  }
}
