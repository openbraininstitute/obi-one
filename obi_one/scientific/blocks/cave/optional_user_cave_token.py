
from obi_one.core.block import Block

from pydantic import Field

class OptionalUserCaveToken(Block):
        
    optional_personal_cave_token: str | None = Field(
        default=None,
        title="Personal CAVE token",
        description="""Optionally, a personal CAVE token can be provided here. This is useful if the task
        is executed in an environment where the secrets file is not accessible, but the user has a personal token they can provide.""",
    )