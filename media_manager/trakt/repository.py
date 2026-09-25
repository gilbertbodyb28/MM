from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.trakt.models import TraktConnection
from media_manager.trakt.schemas import TraktConnectionData


class TraktRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: UUID) -> TraktConnectionData | None:
        row = (
            await self.db.execute(
                select(TraktConnection).where(TraktConnection.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return TraktConnectionData.model_validate(row, from_attributes=True)

    async def upsert(self, connection: TraktConnectionData) -> None:
        row = (
            await self.db.execute(
                select(TraktConnection).where(
                    TraktConnection.user_id == connection.user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = TraktConnection(user_id=connection.user_id)
            self.db.add(row)
        row.access_token = connection.access_token
        row.refresh_token = connection.refresh_token
        row.token_type = connection.token_type
        row.scope = connection.scope
        row.expires_at = connection.expires_at
        row.account_username = connection.account_username
        row.account_slug = connection.account_slug
        row.trakt_user_id = connection.trakt_user_id
        await self.db.commit()

    async def delete(self, user_id: UUID) -> None:
        await self.db.execute(
            delete(TraktConnection).where(TraktConnection.user_id == user_id)
        )
        await self.db.commit()
