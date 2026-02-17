from typing import Annotated

from fastapi import Depends

from app.config import settings


def get_task_callback_url() -> str:
    return f"{settings.SERVICE_BASE_URL}/task/callback"


TaskCallBackUrlDep = Annotated[str, Depends(get_task_callback_url)]
