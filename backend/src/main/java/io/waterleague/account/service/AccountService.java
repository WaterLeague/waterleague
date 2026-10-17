package io.waterleague.account.service;

import io.waterleague.account.dto.AuthRequest;
import io.waterleague.account.dto.RegistrationRequest;
import io.waterleague.account.entity.Account;
import io.waterleague.account.entity.MemberType;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
  private final AccountRepository accounts;
  private final PasswordEncoder encoder;
  private final String dummy;
  private final io.waterleague.district.repository.DistrictRepository districts;

  public AccountService(
      AccountRepository a,
      PasswordEncoder e,
      io.waterleague.district.repository.DistrictRepository districts) {
    accounts = a;
    this.districts = districts;
    encoder = e;
    dummy = e.encode(UUID.randomUUID().toString());
  }

  public Account register(RegistrationRequest dto) {
    districts.require(dto.districtId());
    boolean player = dto.memberType() == MemberType.PLAYER;
    if (player
        ? (!dto.organizationName().isBlank() || !dto.purpose().isBlank())
        : (dto.organizationName().isBlank() || dto.purpose().isBlank()))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var account =
        new Account(
            UUID.randomUUID(),
            dto.username(),
            dto.username(),
            encoder.encode(dto.password()),
            "MEMBER",
            dto.memberType().name(),
            player ? "APPROVED" : "PENDING",
            null,
            dto.organizationName().strip(),
            dto.purpose().strip(),
            true,
            dto.districtId(),
            dto.affiliationType());
    try {
      accounts.add(account);
    } catch (DuplicateKeyException e) {
      throw new DomainException(ErrorCode.ACCOUNT_UNAVAILABLE);
    }
    return account;
  }

  public Account selectDistrict(
      String username, io.waterleague.account.dto.DistrictSelectionRequest dto) {
    var account = current(username);
    districts.require(dto.districtId());
    if (!accounts.selectDistrict(account.id(), dto.districtId(), dto.affiliationType()))
      throw new DomainException(ErrorCode.DISTRICT_ALREADY_SELECTED);
    return current(username);
  }

  public Account login(AuthRequest dto) {
    var a = accounts.byUsername(dto.username());
    boolean match = encoder.matches(dto.password(), a.map(Account::passwordHash).orElse(dummy));
    if (!match || a.isEmpty() || !a.get().enabled())
      throw new DomainException(ErrorCode.CREDENTIALS_INVALID);
    if (!a.get().approvalStatus().equals("APPROVED"))
      throw new DomainException(ErrorCode.ACCOUNT_NOT_APPROVED);
    return a.get();
  }

  public Account current(String username) {
    return accounts
        .byUsername(username)
        .filter(Account::usable)
        .orElseThrow(() -> new DomainException(ErrorCode.AUTHENTICATION_REQUIRED));
  }
}
