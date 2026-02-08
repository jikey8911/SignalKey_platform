from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.security.auth_deps import get_current_user
from api.src.domain.models.schemas import AIAgent

router = APIRouter(prefix="/ai", tags=["ai"])

class AgentUpdate(BaseModel):
    apiKey: Optional[str] = None
    isActive: Optional[bool] = None
    isPrimary: Optional[bool] = None

@router.get("/agents", response_model=List[AIAgent])
async def get_agents(current_user: dict = Depends(get_current_user)):
    """
    Obtiene la lista de agentes de IA configurados para el usuario.
    Si no existen, los crea dinámicamente en la respuesta (o en DB).
    """
    try:
        user_id = current_user["openId"]

        # Obtener config de usuario para vincular
        config = await get_app_config(user_id)
        if not config:
            raise HTTPException(status_code=404, detail="User config not found")

        user_oid = config["userId"]

        # Lista fija de proveedores soportados
        supported_providers = ["gemini", "openai", "perplexity", "grok", "groq"]

        # Obtener agentes existentes de la DB
        existing_agents = await db.ai_agents.find({"userId": user_oid}).to_list(None)
        existing_map = {agent["provider"]: agent for agent in existing_agents}

        response_agents = []

        for provider in supported_providers:
            if provider in existing_map:
                agent_doc = existing_map[provider]
                # Asegurar ID es string para Pydantic si es ObjectId
                if "_id" in agent_doc:
                    agent_doc["_id"] = str(agent_doc["_id"])
                agent_doc["userId"] = str(agent_doc["userId"])
                if "configId" in agent_doc:
                    agent_doc["configId"] = str(agent_doc["configId"])

                response_agents.append(AIAgent(**agent_doc))
            else:
                # Crear estructura default (no guardamos aun en DB para no ensuciar, o si?)
                # Mejor retornamos la estructura, el usuario la guardará al editar
                default_agent = AIAgent(
                    userId=str(user_oid),
                    configId=str(config["_id"]),
                    provider=provider,
                    apiKey="",
                    isActive=False,
                    isPrimary=(provider == "gemini"), # Default primary
                    createdAt=datetime.utcnow()
                )
                response_agents.append(default_agent)

        return response_agents

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/agents/{provider}")
async def update_agent(
    provider: str,
    update: AgentUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza la configuración de un agente de IA.
    """
    try:
        user_id = current_user["openId"]
        config = await get_app_config(user_id)
        if not config:
            raise HTTPException(status_code=404, detail="User config not found")

        user_oid = config["userId"]

        # Validar provider
        if provider not in ["gemini", "openai", "perplexity", "grok", "groq"]:
            raise HTTPException(status_code=400, detail="Invalid AI provider")

        # Preparar datos de actualización
        update_data = {"updatedAt": datetime.utcnow()}
        if update.apiKey is not None:
            update_data["apiKey"] = update.apiKey
            # Si se pone una key, asumimos activo a menos que se diga lo contrario
            if update.isActive is None and update.apiKey:
                update_data["isActive"] = True

        if update.isActive is not None:
            update_data["isActive"] = update.isActive

        if update.isPrimary is not None:
            update_data["isPrimary"] = update.isPrimary

            # Si este se vuelve primario, desactivar el flag isPrimary en los otros
            if update.isPrimary:
                await db.ai_agents.update_many(
                    {"userId": user_oid, "provider": {"$ne": provider}},
                    {"$set": {"isPrimary": False}}
                )

        # Upsert
        result = await db.ai_agents.update_one(
            {"userId": user_oid, "provider": provider},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "userId": user_oid,
                    "configId": config["_id"],
                    "createdAt": datetime.utcnow(),
                    # Si no se pasó en update, defaults:
                    "apiKey": update.apiKey or "",
                    "isActive": update.isActive if update.isActive is not None else False,
                    "isPrimary": update.isPrimary if update.isPrimary is not None else False
                }
            },
            upsert=True
        )

        return {"success": True, "message": f"Agent {provider} updated"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
