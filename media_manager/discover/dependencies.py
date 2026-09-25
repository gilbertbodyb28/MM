from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from media_manager.database import DbSessionDependency
from media_manager.discover.provider import TmdbDiscoverProvider
from media_manager.discover.service import DiscoverService


async def get_discover_provider() -> AsyncIterator[TmdbDiscoverProvider]:
    provider = TmdbDiscoverProvider()
    try:
        yield provider
    finally:
        await provider.close()


discover_provider_dep = Annotated[TmdbDiscoverProvider, Depends(get_discover_provider)]


def get_discover_service(
    db_session: DbSessionDependency,
    provider: discover_provider_dep,
) -> DiscoverService:
    return DiscoverService(provider=provider, db_session=db_session)


discover_service_dep = Annotated[DiscoverService, Depends(get_discover_service)]
