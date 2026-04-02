from typing import Annotated

from fastapi import Depends

from app.config import settings


def get_task_callback_url() -> str:
    return settings.API_URL


CallBackUrlDep = Annotated[str, Depends(get_task_callback_url)]
