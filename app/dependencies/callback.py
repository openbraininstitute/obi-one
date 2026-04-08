from typing import Annotated

from fastapi import Depends

from app.config import settings


def get_task_callback_url() -> str:
    return f"{settings.API_URL}/declared/task/callback"


CallBackUrlDep = Annotated[str, Depends(get_task_callback_url)]
