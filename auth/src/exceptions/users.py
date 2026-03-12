class UserAlreadyExists(Exception):
    def __init__(self, already_used_field: str) -> None:
        self.message = f"field {already_used_field} already use"


class InvalidCredentials(Exception):
    def __init__(self, message: str | None = None) -> None:
        if message is None:
            self.message = "Invalid credentials"
        else:
            self.message = f"Invalid credentials: {message}"
