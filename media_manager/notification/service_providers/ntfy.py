import httpx

from media_manager.config import MediaManagerConfig
from media_manager.notification.schemas import MessageNotification
from media_manager.notification.service_providers.abstract_notification_service_provider import (
    AbstractNotificationServiceProvider,
)


class NtfyNotificationServiceProvider(AbstractNotificationServiceProvider):
    """
    Ntfy Notification Service Provider
    """

    def __init__(self) -> None:
        self.config = MediaManagerConfig().notifications.ntfy

    async def send_notification(self, message: MessageNotification) -> bool:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url=self.config.url,
                content=message.message.encode(encoding="utf-8"),
                headers={
                    "Title": "MediaManager - " + message.title,
                },
            )
        if response.status_code not in range(200, 300):
            return False
        return True
