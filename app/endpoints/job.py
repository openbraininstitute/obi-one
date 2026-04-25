from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.launch_system import LaunchSystemAsyncClientDep, LaunchSystemClientDep
from app.schemas.job import JobRead
from app.services import job as job_service

router = APIRouter(
    prefix="/job",
    tags=["job"],
    dependencies=[Depends(user_verified)],
)


@router.get("/{job_id}")
def read_job(
    job_id: UUID,
    user_context: UserContextDep,  # noqa: ARG001
    ls_client: LaunchSystemClientDep,
) -> JobRead:
    """Proxy GET /{job_id} to the launch-system."""
    return job_service.read_job(job_id, ls_client)


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: UUID,
    user_context: UserContextDep,  # noqa: ARG001
    ls_async_client: LaunchSystemAsyncClientDep,
) -> StreamingResponse:
    """Proxy GET /{job_id}/stream from the launch-system as NDJSON."""
    line_iterator = await job_service.stream_job(job_id, ls_async_client)
    return StreamingResponse(
        content=line_iterator,
        media_type="application/x-ndjson",
    )
