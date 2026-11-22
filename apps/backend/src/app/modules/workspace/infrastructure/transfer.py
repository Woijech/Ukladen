from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.workspace.infrastructure.orm import TransferReceiptModel


class SqlAlchemyTransferReceipts:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, digest: str) -> UUID | None:
        receipt = self.session.get(TransferReceiptModel, (user_id, digest))
        return receipt.root_page_id if receipt else None

    def save(self, user_id: UUID, digest: str, root_page_id: UUID) -> None:
        self.session.add(
            TransferReceiptModel(
                user_id=user_id,
                digest=digest,
                root_page_id=root_page_id,
            )
        )
        self.session.flush()
