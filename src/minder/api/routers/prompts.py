import uuid
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from minder.observability.metrics import record_admin_operation
from minder.store.interfaces import IOperationalStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/prompts",
    tags=["prompts"],
)


class PromptCreate(BaseModel):
    name: str
    title: str
    description: str
    content_template: str
    arguments: List[str] = Field(default_factory=list)


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    content_template: Optional[str] = None
    arguments: Optional[List[str]] = None


class PromptResponse(BaseModel):
    id: str
    name: str
    title: str
    description: str
    content_template: str
    arguments: List[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def get_store(request: Request) -> IOperationalStore:
    return request.app.state.store


@router.get("", response_model=List[PromptResponse])
async def list_prompts(store: IOperationalStore = Depends(get_store)):
    await record_admin_operation(
        operation="list_prompts", outcome="success", actor_id="system", store=store
    )
    try:
        prompts = await store.list_prompts()
        return [
            PromptResponse(
                id=str(p.id),
                name=p.name,
                title=p.title,
                description=p.description,
                content_template=p.content_template,
                arguments=p.arguments,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in prompts
        ]
    except Exception as e:
        logger.exception("Failed to list prompts", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    payload: PromptCreate, store: IOperationalStore = Depends(get_store)
):
    await record_admin_operation(
        operation="create_prompt", outcome="success", actor_id="system", store=store
    )
    try:
        prompt = await store.create_prompt(
            name=payload.name,
            title=payload.title,
            description=payload.description,
            content_template=payload.content_template,
            arguments=payload.arguments,
        )
        return PromptResponse(
            id=str(prompt.id),
            name=prompt.name,
            title=prompt.title,
            description=prompt.description,
            content_template=prompt.content_template,
            arguments=prompt.arguments,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )
    except Exception as e:
        logger.exception("Failed to create prompt", exc_info=e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: uuid.UUID, store: IOperationalStore = Depends(get_store)
):
    await record_admin_operation(
        operation="get_prompt", outcome="success", actor_id="system", store=store
    )
    try:
        prompt = await store.get_prompt_by_id(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return PromptResponse(
            id=str(prompt.id),
            name=prompt.name,
            title=prompt.title,
            description=prompt.description,
            content_template=prompt.content_template,
            arguments=prompt.arguments,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get prompt", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{prompt_id}", response_model=PromptResponse)
@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: uuid.UUID,
    payload: PromptUpdate,
    store: IOperationalStore = Depends(get_store),
):
    await record_admin_operation(
        operation="update_prompt", outcome="success", actor_id="system", store=store
    )
    try:
        update_data = payload.model_dump(exclude_unset=True)
        prompt = await store.update_prompt(prompt_id, **update_data)
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return PromptResponse(
            id=str(prompt.id),
            name=prompt.name,
            title=prompt.title,
            description=prompt.description,
            content_template=prompt.content_template,
            arguments=prompt.arguments,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update prompt", exc_info=e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: uuid.UUID, store: IOperationalStore = Depends(get_store)
):
    await record_admin_operation(
        operation="delete_prompt", outcome="success", actor_id="system", store=store
    )
    try:
        await store.delete_prompt(prompt_id)
    except Exception as e:
        logger.exception("Failed to delete prompt", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
