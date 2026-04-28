from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies.accounting import AccountingSessionFactoryDep
from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskAccountingInfo
from app.services import accounting as accounting_service
from app.types import TaskType

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/circuit-extraction/estimate",
    summary="Estimate circuit extraction cost.",
    description="Estimate accounting cost for a circuit extraction task config.",
)
def estimate_circuit_extraction_cost(
    config_id: UUID,
    db_client: DatabaseClientDep,
    _user_context: UserContextWithProjectIdDep,
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskAccountingInfo:
    return accounting_service.estimate_task_cost(
        db_client=db_client,
        config_id=config_id,
        project_context=db_client.project_context,
        accounting_factory=accounting_factory,
        task_definition=TASK_DEFINITIONS[TaskType.circuit_extraction],
    )
