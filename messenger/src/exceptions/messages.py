from uuid import UUID


class NotDialogParticipantError(Exception):
    """Raised when a user tries to send a message to a dialog they don't belong to."""

    def __init__(self, user_id: UUID, dialog_id: UUID) -> None:
        self.user_id = user_id
        self.dialog_id = dialog_id
        super().__init__(f"User '{user_id}' is not a participant of dialog '{dialog_id}'")


class ClientMessageIdConflictError(Exception):
    """Raised when client_message_id was already used in a different context."""

    def __init__(self, client_message_id: str) -> None:
        self.client_message_id = client_message_id
        super().__init__(f"client_message_id '{client_message_id}' already used")


class DialogNotFoundError(Exception):
    """Raised when the dialog does not exist."""

    def __init__(self, dialog_id: UUID) -> None:
        self.dialog_id = dialog_id
        super().__init__(f"Dialog '{dialog_id}' not found")


class MessageNotFoundError(Exception):
    """Raised when the message does not exist."""

    def __init__(self, message_id: UUID) -> None:
        self.message_id = message_id
        super().__init__(f"Message '{message_id}' not found")
