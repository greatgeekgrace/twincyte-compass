import gzip
import json
from pathlib import Path

import httpx

ATLAS = json.load(gzip.open(Path(__file__).with_name("atlas.json.gz"), "rt"))
PROGRAMS = ATLAS["programs"]
_http = httpx.AsyncClient(timeout=20)
_info: dict = {}


def _percentile(strength, pct):
    p50, p75, p90, p99 = pct
    if strength >= p99:
        return "top 1%"
    if strength >= p90:
        return "top 10%"
    if strength >= p75:
        return "top 25%"
    if strength >= p50:
        return "above median"
    return "below median"


def lookup(gene):
    """Return what turning this gene down does in each cell line we have data for."""
    g = gene.strip().upper()
    out = {"gene": g, "lines": []}
    for key, line in ATLAS["lines"].items():
        p = line["perturbations"].get(g)
        if not p:
            continue
        progs = sorted(({"program": PROGRAMS[k], "key": k, "z": v} for k, v in p["programs"].items()), key=lambda x: -abs(x["z"]))
        out["lines"].append({
            "line": key, "description": line["line"], "screen": p["source"],
            "knockdown": p["knockdown"], "cells": p["cells"], "significant": p["significant"],
            "effect_size": p["strength"], "effect_rank": _percentile(p["strength"], line["strength_pct_50_75_90_99"]),
            "genes_changed": p["n_changed"], "programs": progs,
            "most_up": p["up"][:12], "most_down": p["down"][:12], "acts_like": p["similar"][:8],
        })
    out["found"] = bool(out["lines"])
    return out


def known(gene):
    g = gene.strip().upper()
    return any(g in line["perturbations"] for line in ATLAS["lines"].values())


async def gene_info(gene):
    g = gene.strip().upper()
    if g in _info:
        return _info[g]
    try:
        r = await _http.get("https://mygene.info/v3/query", params={"q": f"symbol:{g}", "species": "human", "fields": "name,summary,entrezgene,alias", "size": 1})
        hit = (r.json().get("hits") or [{}])[0]
    except Exception:
        hit = {}
    info = {"symbol": g, "name": hit.get("name"), "summary": hit.get("summary"), "entrez": hit.get("entrezgene")}
    links = {"ClinicalTrials.gov": f"https://clinicaltrials.gov/search?term={g}"}
    if info["entrez"]:
        links["NCBI Gene"] = f"https://www.ncbi.nlm.nih.gov/gene/{info['entrez']}"
    links["MedlinePlus Genetics"] = f"https://medlineplus.gov/genetics/gene/{g.lower()}/"
    info["links"] = links
    _info[g] = info
    return info
