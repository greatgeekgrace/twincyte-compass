import asyncio
import json
import re
from datetime import date

from . import cell, llm, qloo

SUPPORT_TAGS = [
    "urn:tag:keyword:qloo:rare_disease",
    "urn:tag:theme:qloo:chronic_illness",
    "urn:tag:keyword:qloo:chronic_illness",
    "urn:tag:theme:qloo:childhood_illness",
    "urn:tag:keyword:qloo:sick_children",
    "urn:tag:motif:qloo:caregiver_support",
    "urn:tag:theme:qloo:caregiver_support",
]
CALM_PLACE_TAGS = [f"urn:tag:category:place:{t}" for t in (
    "park", "garden", "botanical_garden", "aquarium", "library", "children_s_museum", "childrens_museum", "nature_preserve", "playground")]
AVOID_PLACE_TAGS = [f"urn:tag:{k}:place:{t}" for t in ("cemetery", "memorial") for k in ("category", "genre")]

PODCAST_QUERIES = {
    "parent": ["special needs parenting", "medical parenting", "rare disease", "parenting disabilities", "caregiver"],
    "self": ["rare disease", "chronic illness", "disability", "living with illness"],
    "family": ["caregiver", "rare disease", "chronic illness", "grief"],
}
TOPIC = re.compile(r"rare (disease|life)|ultra rare|illness|disease|disab|special needs|unique needs|caregiv|carer|patient|medical|chronic|epilep|autism|grief", re.I)
AVOID = re.compile(r"essential oil|holistic|natural remed|\bcure\b|heal (your|chronic)|healing|detox|medical medium|lyme|anti-?vax|miracle|naturopath|functional medicine|guitar|medium rare|steak|wine", re.I)
AVOID_PLACE = re.compile(r"cemetery|graveyard|burying ground|holocaust|funeral|crematori|memorial(?! (library|hall|park|garden|hospital))", re.I)

READERS = {
    "parent": "a parent or carer of a child with this condition",
    "self": "an adult living with this condition",
    "family": "a relative or friend who wants to understand",
}

DISCLAIMER = ("Research data from human cell lines in a lab, not from patients. It shows what happens inside a cell when this gene is "
              "turned down, and cannot predict symptoms, severity or treatment. Please talk to your care team.")


def _favs(profile):
    favs = [f for f in profile.get("favorites", []) if f.get("id")]
    return favs, [f["id"] for f in favs], {f["id"]: f["name"] for f in favs}


async def explain_cell(profile, data, info):
    if not data["found"]:
        return None
    reader = READERS.get(profile.get("reader"), READERS["family"])
    prompt = f"""You are writing for {reader}. Condition (as they described it): {profile.get('condition') or 'not given'}.
Gene: {data['gene']} — {info.get('name') or ''}.
Reference summary (NCBI, may be technical): {(info.get('summary') or 'none')[:900]}
Cell data (CRISPR knockdown of this gene in human cell lines, Replogle et al. 2022; program z-scores are averages over the program's genes, positive = turned up, negative = turned down; acts_like = genes whose knockdown looks most similar): {json.dumps(data['lines'])[:6000]}

Write plain, warm, precise English for a non-scientist. Do not mention "the reference summary", "the data provided" or JSON; just explain. Only state what the data or the reference summary supports. Never predict symptoms, severity, prognosis or treatment. Explain any term you use.
Return JSON only:
{{"headline": "one sentence, what this gene's job is",
  "gene_job": "2-3 sentences: what this gene normally does, from the reference summary",
  "cell_story": ["3-4 short bullets: what the cell data shows when the gene is turned down, naming the biggest programs and whether the effect is strong compared with other genes (use effect_rank)"],
  "family_of_genes": "1-2 sentences about the acts_like genes and what they have in common, only if obvious from their names; else say they share a similar fingerprint",
  "questions_for_care_team": ["3 good questions to bring to the next appointment"]}}"""
    msg = await llm.chat([{"role": "system", "content": "You explain biology to families with care and precision. Output strict JSON."},
                          {"role": "user", "content": prompt}], temperature=0.3)
    txt = (msg.get("content") or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


async def explain(profile):
    gene = (profile.get("gene") or "").strip().upper()
    if not gene:
        return None
    data = cell.lookup(gene)
    info = await cell.gene_info(gene)
    if not data["found"] and not info.get("summary"):
        return None
    return await explain_cell(profile, data, info) if data["found"] else None


async def build_compass(profile):
    gene = (profile.get("gene") or "").strip().upper()
    favs, ids, names = _favs(profile)
    city = profile.get("city")

    async def rec(kind, **kw):
        try:
            items = await qloo.recommend(kind, names=names, take=8, **kw)
        except qloo.QlooError:
            return []
        return [i for i in items if not i.get("closed")]

    async def rec_or_broaden(kind):
        items = await rec(kind, signal_ids=ids, tag_ids=SUPPORT_TAGS)
        if len(items) < 3:
            seen = {i["id"] for i in items}
            items += [i for i in await rec(kind, tag_ids=SUPPORT_TAGS) if i["id"] not in seen]
        return items

    async def podcast_picks():
        found = await asyncio.gather(*[qloo.search(q, "podcast", take=8) for q in PODCAST_QUERIES.get(profile.get("reader"), PODCAST_QUERIES["family"])],
                                     return_exceptions=True)
        cands = {e["id"]: e for hits in found if isinstance(hits, list) for e in hits
                 if TOPIC.search(e["name"] or "") and not AVOID.search(e["name"] or "")}
        if not cands:
            return []
        if not ids:
            return list(cands.values())[:6]
        try:
            ranked = await qloo.recommend("podcast", signal_ids=ids, names=names, take=8, result_ids=list(cands))
        except qloo.QlooError:
            ranked = []
        return [r for r in ranked if r["id"] in cands] or list(cands.values())[:6]

    async def cell_part():
        info = await cell.gene_info(gene) if gene else {}
        data = cell.lookup(gene) if gene else {"found": False, "lines": [], "gene": gene}
        return {"gene": gene, "info": info, "data": data, "story": None, "disclaimer": DISCLAIMER}

    jobs = [
        cell_part(),
        rec_or_broaden("book"),
        podcast_picks(),
        rec("movie", signal_ids=ids),
        rec("tv_show", signal_ids=ids),
        rec("place", signal_ids=ids, tag_ids=CALM_PLACE_TAGS, exclude_tag_ids=AVOID_PLACE_TAGS, city=city) if city else asyncio.sleep(0, result=[]),
    ]
    cellres, books, pods, movies, shows, places = await asyncio.gather(*jobs)
    places = [p for p in places if not AVOID_PLACE.search(p.get("name") or "")]
    books = [b for b in books if not AVOID.search(b.get("name") or "")]
    sections = [
        {"key": "read", "title": "To read, when you're ready", "note": "Books about living with illness, caring and genetics, ranked by your family's taste.", "items": books[:6]},
        {"key": "listen", "title": "To listen to on the long days", "note": "Podcasts on the same themes, matched to what you already love.", "items": pods[:6]},
        {"key": "rest", "title": "A night off", "note": "Nothing about illness. Just things people with your taste love.", "items": (movies[:4] + shows[:3])},
        {"key": "breathe", "title": f"Places to breathe in {city}" if city else "Places to breathe", "note": "Calm places near you, chosen by your taste.", "items": places[:6]},
    ]
    return {"cell": cellres, "sections": [s for s in sections if s["items"]], "reader": profile.get("reader")}


TOOLS = [
    {"type": "function", "function": {
        "name": "cell_lookup",
        "description": "What happens inside a human cell when a gene is turned down (CRISPRi Perturb-seq data, K562 blood cells and RPE1 retinal cells). Returns effect size and rank, cell programs that change, most changed genes and genes that act alike.",
        "parameters": {"type": "object", "required": ["gene"], "properties": {"gene": {"type": "string", "description": "HGNC symbol, e.g. RPS19"}}}}},
    {"type": "function", "function": {
        "name": "gene_info",
        "description": "Official name and NCBI summary of a human gene, plus trusted links (NCBI Gene, MedlinePlus Genetics, ClinicalTrials.gov search).",
        "parameters": {"type": "object", "required": ["gene"], "properties": {"gene": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "find_tags",
        "description": "Turn a need into Qloo tag ids (e.g. 'grief', 'hope', 'explaining illness to children', 'quiet', 'accessible').",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"}, "for_kind": {"type": "string", "enum": list(qloo.TYPES)}}}}},
    {"type": "function", "function": {
        "name": "recommend",
        "description": "Taste-matched recommendations from Qloo using the family's favourites as signals. Each result says which favourites drove it ('because').",
        "parameters": {"type": "object", "required": ["kind"], "properties": {
            "kind": {"type": "string", "enum": list(qloo.TYPES)},
            "tag_ids": {"type": "array", "items": {"type": "string"}},
            "city": {"type": "string", "description": "Only for places; defaults to the family's city"},
            "take": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "search_entities",
        "description": "Find a specific book, film, show, artist, podcast or place in Qloo by name.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"}, "kind": {"type": "string", "enum": list(qloo.TYPES)}}}}},
]

SYSTEM = """You are Twincyte Compass, a companion for families on a rare-disease journey. Today is {today}.
You are talking with {reader}. Condition (their words): {condition}. Gene: {gene}. City: {city}.
The family's favourites (Qloo ids): {favs}.

Two kinds of help, both grounded in tools:
1. Understanding: use cell_lookup and gene_info. Explain in plain language what the cell data shows. It is lab data from cell lines, not from this patient: never predict symptoms, severity, prognosis or treatment, and say so when asked. Encourage questions for the care team.
2. Support that fits them: use recommend / find_tags so every book, podcast, film or place is real and matched to their tastes. Use the 'because' field to say why.
If asked to explain the condition to a child, you may use analogies drawn from the family's favourites, but keep facts to what the tools returned.
Be gentle and brief: a sentence of framing, then at most 5 bullets. Never invent places, titles, statistics or organisations."""


async def run_chat(profile, history, max_steps=6):
    favs, ids, names = _favs(profile)
    msgs = [{"role": "system", "content": SYSTEM.format(
        today=date.today().isoformat(), reader=READERS.get(profile.get("reader"), READERS["family"]),
        condition=profile.get("condition") or "not given", gene=profile.get("gene") or "not given",
        city=profile.get("city") or "not given",
        favs=json.dumps([{"id": f["id"], "name": f["name"], "type": f.get("type")} for f in favs]))}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history[-16:] if m.get("role") in ("user", "assistant")]
    cards, trace = [], []
    for _ in range(max_steps):
        msg = await llm.chat(msgs, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": msg.get("content") or "", "cards": cards[:10], "trace": trace}
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                a = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                a = {}
            try:
                if name == "cell_lookup":
                    res = cell.lookup(a["gene"])
                elif name == "gene_info":
                    res = await cell.gene_info(a["gene"])
                elif name == "find_tags":
                    res = await qloo.find_tags(a["query"], a.get("for_kind"), take=6)
                elif name == "recommend":
                    city = (a.get("city") or profile.get("city")) if a["kind"] == "place" else None
                    res = await qloo.recommend(a["kind"], signal_ids=ids, names=names, city=city,
                                               tag_ids=a.get("tag_ids") or [], take=min(int(a.get("take") or 6), 10))
                    res = [r for r in res if not r.get("closed")]
                    cards.extend(res)
                elif name == "search_entities":
                    res = await qloo.search(a["query"], a.get("kind"), take=5)
                else:
                    res = {"error": "unknown tool"}
            except (qloo.QlooError, KeyError) as e:
                res = {"error": str(e)}
            trace.append({"tool": name, "args": a})
            msgs.append({"role": "tool", "tool_call_id": c.get("id", name), "name": name, "content": json.dumps(res)[:20000]})
    return {"reply": "Here's what I found so far.", "cards": cards[:10], "trace": trace}
