import asyncio
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, cell, llm, qloo

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="Twincyte Compass")
HITS = defaultdict(deque)
LIMIT = int(os.environ.get("REQUESTS_PER_HOUR", "80"))
ALL_GENES = sorted({g for line in cell.ATLAS["lines"].values() for g in line["perturbations"]})


def limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = HITS[ip], time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= LIMIT:
        raise HTTPException(429, "Demo rate limit reached — please try again later.")
    q.append(now)


class Fav(BaseModel):
    name: str = Field(max_length=120)
    kind: str | None = None


class ResolveIn(BaseModel):
    favorites: list[Fav] = Field(max_length=10)


class Profile(BaseModel):
    gene: str | None = Field(default=None, max_length=20)
    condition: str | None = Field(default=None, max_length=120)
    reader: str = "parent"
    city: str | None = Field(default=None, max_length=80)
    needs: str | None = Field(default=None, max_length=400)
    favorites: list[dict] = Field(default_factory=list, max_length=10)


class ChatIn(BaseModel):
    profile: Profile
    history: list[dict]


@app.get("/api/health")
async def health():
    return {"ok": True, "model": llm.MODEL, "genes_in_atlas": len(ALL_GENES)}


@app.get("/api/genes")
async def genes(q: str = ""):
    q = q.strip().upper()
    if not q:
        return []
    exact = [g for g in ALL_GENES if g == q]
    return exact + [g for g in ALL_GENES if g.startswith(q) and g != q][:12]


@app.get("/api/cell/{gene}")
async def cell_view(gene: str):
    return {"data": cell.lookup(gene), "info": await cell.gene_info(gene)}


@app.post("/api/resolve")
async def resolve(body: ResolveIn, request: Request):
    limit(request)

    async def one(f: Fav):
        try:
            hits = await qloo.search(f.name, f.kind, take=4)
        except qloo.QlooError:
            hits = []
        return {"input": f.name, "kind": f.kind, "matches": hits}

    return await asyncio.gather(*[one(f) for f in body.favorites])


@app.post("/api/compass")
async def compass(body: Profile, request: Request):
    limit(request)
    return await agent.build_compass(body.model_dump())


@app.post("/api/explain")
async def explain(body: Profile, request: Request):
    limit(request)
    return {"story": await agent.explain(body.model_dump())}


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    limit(request)
    return await agent.run_chat(body.profile.model_dump(), body.history)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
