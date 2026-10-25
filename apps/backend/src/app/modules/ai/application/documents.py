from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DocumentStep:
    run_id: UUID
    user_id: UUID
    lease: UUID
    phase: str
    question: str
    evidence: str
    next_offset: int = 0
    characters: int = 0


class DocumentSteps(Protocol):
    def claim(self, run_id: UUID) -> DocumentStep | None: ...
    def complete(self, step: DocumentStep, answer: str) -> bool: ...
    def fail(self, step: DocumentStep, error: Exception) -> None: ...


class DocumentModel(Protocol):
    def generate(self, step: DocumentStep) -> str: ...


class DocumentAnalysisService:
    """One durable unit per dispatch; source length never consumes a user allowance."""

    def __init__(self, steps: DocumentSteps, model: DocumentModel):
        self.steps, self.model = steps, model

    def process(self, run_id: UUID) -> bool:
        step = self.steps.claim(run_id)
        if step is None:
            return False
        try:
            answer = self.model.generate(step)
            if not answer.strip() or len(answer.encode()) > (
                16384 if step.phase == "final" else 1500
            ):
                raise ValueError("Invalid document-processing response.")
            return self.steps.complete(step, answer)
        except Exception as error:
            self.steps.fail(step, error)
            raise
