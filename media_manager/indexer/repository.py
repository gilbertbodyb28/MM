import logging

from sqlalchemy.ext.asyncio import AsyncSession

from media_manager.indexer.models import IndexerQueryResult
from media_manager.indexer.schemas import (
    IndexerQueryResult as IndexerQueryResultSchema,
)
from media_manager.indexer.schemas import (
    IndexerQueryResultId,
)

log = logging.getLogger(__name__)


class IndexerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_result(
        self, result_id: IndexerQueryResultId
    ) -> IndexerQueryResultSchema:
        return IndexerQueryResultSchema.model_validate(
            await self.db.get(IndexerQueryResult, result_id)
        )

    async def save_result(
        self, result: IndexerQueryResultSchema
    ) -> IndexerQueryResultSchema:
        await self.save_results([result])
        return result

    async def save_results(
        self, results: list[IndexerQueryResultSchema]
    ) -> list[IndexerQueryResultSchema]:
        """Persist a search result batch with one transaction commit."""
        if not results:
            return results

        db_results = []
        for result in results:
            result_data = result.model_dump()
            # SQLAlchemy cannot persist URL-like Pydantic values directly.
            result_data["download_url"] = str(result.download_url)
            db_results.append(IndexerQueryResult(**result_data))

        self.db.add_all(db_results)
        await self.db.commit()
        return results
