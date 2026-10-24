from dataclasses import dataclass

from app.modules.ai.domain.state import InvalidAiState


@dataclass(frozen=True)
class AssistantPreferences:
    instructions: str = ""
    version: int = 0

    def __post_init__(self) -> None:
        try:
            size = len(self.instructions.encode("utf-8"))
        except UnicodeEncodeError:
            raise InvalidAiState("Invalid instructions encoding.") from None
        if size > 8192 or "\x00" in self.instructions or self.version < 0:
            raise InvalidAiState("Invalid assistant preferences.")
