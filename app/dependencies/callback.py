from typing import Annotated

from fastapi import Depends, Request


def get_task_callback_url(request: Request) -> str:
    return f"{request.base_url}declared/task/callback"


CallBackUrlDep = Annotated[str, Depends(get_task_callback_url)]
