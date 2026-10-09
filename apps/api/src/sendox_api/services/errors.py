"""Domain errors, mapped to HTTP status codes in one place by the routers."""


class DomainError(Exception):
    """Base class so a router can catch everything the services raise."""


class EmailAlreadyRegistered(DomainError):
    pass


class WeakPassword(DomainError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class InvalidCredentials(DomainError):
    pass


class EmailNotVerified(DomainError):
    pass


class AccountInactive(DomainError):
    pass


class TokenNotUsable(DomainError):
    """Unknown, already consumed, or expired."""


class NotAMember(DomainError):
    pass


class InsufficientRole(DomainError):
    def __init__(self, required: str, actual: str) -> None:
        self.required = required
        self.actual = actual
        super().__init__(f"requires {required}, caller is {actual}")


class LastOwner(DomainError):
    """A workspace must keep at least one owner."""


class SlugTaken(DomainError):
    pass


class AlreadyInvited(DomainError):
    pass


class AlreadyAMember(DomainError):
    pass
