class SelfDialogError(Exception):
    """Raised when a user tries to create a dialog with themselves."""


class UserNotFoundError(Exception):
    """Raised when the target user login does not exist."""

    def __init__(self, login: str) -> None:
        self.login = login
        super().__init__(f"User with login '{login}' not found")


class AuthServiceUnavailableError(Exception):
    """Raised when the auth gRPC service is unreachable."""
