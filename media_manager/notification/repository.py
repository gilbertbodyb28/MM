import logging

from sqlalchemy import delete, select, update
from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import false

from media_manager.exceptions import ConflictError, NotFoundError
from media_manager.notification.models import Notification
from media_manager.notification.schemas import (
    Notification as NotificationSchema,
)
from media_manager.notification.schemas import (
    NotificationId,
)

log = logging.getLogger(__name__)


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_notification(self, nid: NotificationId) -> NotificationSchema:
        result = await self.db.get(Notification, nid)

        if not result:
            msg = f"Notification with id {nid} not found."
            raise NotFoundError(msg)

        return NotificationSchema.model_validate(result)

    async def get_unread_notifications(self) -> list[NotificationSchema]:
        try:
            stmt = (
                select(Notification)
                .where(Notification.read == false())
                .order_by(Notification.timestamp.desc())
            )
            results = (await self.db.execute(stmt)).scalars().all()
            return [
                NotificationSchema.model_validate(notification)
                for notification in results
            ]
        except SQLAlchemyError:
            log.exception("Database error while retrieving unread notifications")
            raise

    async def get_all_notifications(self) -> list[NotificationSchema]:
        try:
            stmt = select(Notification).order_by(Notification.timestamp.desc())
            results = (await self.db.execute(stmt)).scalars().all()
            return [
                NotificationSchema.model_validate(notification)
                for notification in results
            ]
        except SQLAlchemyError:
            log.exception("Database error while retrieving notifications")
            raise

    async def save_notification(self, notification: NotificationSchema) -> None:
        try:
            self.db.add(
                Notification(
                    id=notification.id,
                    read=notification.read,
                    timestamp=notification.timestamp,
                    message=notification.message,
                )
            )
            await self.db.commit()
        except IntegrityError:
            # AsyncSession leaves the txn in invalid state on IntegrityError;
            # without rollback the request-end commit raises PendingRollbackError.
            await self.db.rollback()
            log.exception("Could not save notification")
            msg = f"Notification with id {notification.id} already exists."
            raise ConflictError(msg) from None
        return

    async def mark_notification_as_read(self, nid: NotificationId) -> None:
        stmt = update(Notification).where(Notification.id == nid).values(read=True)
        await self.db.execute(stmt)
        return

    async def mark_notification_as_unread(self, nid: NotificationId) -> None:
        stmt = update(Notification).where(Notification.id == nid).values(read=False)
        await self.db.execute(stmt)
        return

    async def delete_notification(self, nid: NotificationId) -> None:
        stmt = delete(Notification).where(Notification.id == nid)
        result = await self.db.execute(stmt)
        if result.rowcount == 0:
            msg = f"Notification with id {nid} not found."
            raise NotFoundError(msg)
        await self.db.commit()
        return
