"""API routes."""
    #this is where the outside talk to the system
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
#APIRouter-this make us to group related API endpoints together
#pydantic is used for the data validation 
from app.agent.graph import run_agent  
from app.core.config import ConfigError

router = APIRouter()


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentRunResponse(BaseModel):
    response: str


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

#when api post comes to /api/agent/run API execute this function
@router.post("/api/agent/run", response_model=AgentRunResponse)
def run(request: AgentRunRequest) -> AgentRunResponse:
    
    try:
        response = run_agent(request.message) #here now we leave the API page andgo to the app/agent/graph.py 
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent failed: {exc}") from exc
    return AgentRunResponse(response=response)
