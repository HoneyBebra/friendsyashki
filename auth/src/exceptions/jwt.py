class WrongTokenType(Exception):
    def __init__(self) -> None:
        self.message = "Put wrong token type"
