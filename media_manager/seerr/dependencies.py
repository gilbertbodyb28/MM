from typing import Annotated

from fastapi import Depends

from media_manager.seerr.service import SeerrService


def get_seerr_service() -> SeerrService:
    return SeerrService()


seerr_service_dep = Annotated[SeerrService, Depends(get_seerr_service)]
