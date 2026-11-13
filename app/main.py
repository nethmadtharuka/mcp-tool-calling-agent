"""FastAPI application entrypoint."""

import logging
import os

from fastapi import FastAPI  #here we are importing the FastAPI class
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router #here what is telling is Go into app/api/routes.py and get the object called router

# INFO so the tool-calling steps (agent_node/tool_node logger.info calls)
# show up in the console. Plain stdlib logging - no framework.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Production-Oriented AI Engineering Agent", version="0.1.0")
app.include_router(router) #here we are telling dont add all  end point in here (main.py),register them in the defined routes.py

# Browser frontend hosted on another origin (e.g. Vercel). Off unless
# CORS_ALLOW_ORIGINS lists exact origins, comma-separated. Local dev
# doesn't need it: the Vite dev server proxies to this API.
_cors_origins = [o.strip().rstrip("/") for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

#app = FastAPI(title="Production-Oriented AI Engineering Agent", version="0.1.0")
#this is appeared in the automatically generated *API* documentation

