# Twincyte Compass

**A companion for rare-disease families: what the gene does inside a human cell, in plain words — and support that fits your family's taste.**

**Live demo:** https://twincyte-compass.onrender.com (free instance — the first load can take ~50 s to wake up). Click **try an example family**.

> Not medical advice. Cell data comes from lab cell lines, not from any patient.

## Why

A rare diagnosis usually arrives as a gene name and a wall of jargon. Families then spend months searching for two things: *what is actually going on*, and *what helps us cope*. Generic advice ("join a support group", "read about it") ignores who the family is. Twincyte Compass does both halves:

1. **Inside the cell** — Twincyte's virtual-cell atlas shows what happens in real human cells when that gene is turned down, explained in plain language.
2. **Support that fits** — Qloo's taste graph finds books, podcasts, films and calm places that match what this family already loves, and says why.

The second half only works with Qloo: the taste matching, the cross-domain jump (a film the kids love → a podcast for the parent), the "because you love …" explanations and the local places all come from the taste graph.

## What it does

- **Gene → cell programs.** For ~9,900 genes in blood cells (K562) and ~2,400 in near-normal retinal cells (RPE1), the atlas shows effect size versus all genes tested, how much the gene was turned down, and which cell programs move: making proteins, ribosome building, DNA-damage alarm (p53), stress, cell division, energy, cholesterol, red-blood-cell identity.
- **"Acts like" genes.** Genes whose knockdown leaves the most similar fingerprint. For RPS19 (Diamond-Blackfan anemia) these are other ribosomal proteins; for TCOF1 (Treacher Collins syndrome) they include POLR1C and POLR1E — genes behind the same syndrome, recovered from data alone.
- **Plain-language explanation** written by the model only from the data and the NCBI gene summary, with **questions to bring to the care team** and trusted links (NCBI Gene, MedlinePlus Genetics, ClinicalTrials.gov).
- **Support that fits**, chosen by the family's favourites:
  - *To read* — books tagged rare disease, chronic or childhood illness, caregiver support;
  - *To listen* — podcasts found by topic, then ranked by the family's taste (`filter.results.entities` + taste signals);
  - *A night off* — films and shows that have nothing to do with illness;
  - *Places to breathe* — parks, gardens, aquariums, libraries, children's museums near you (cemeteries and memorial sites excluded).
- **Ask Compass** — a tool-calling agent that can look up genes, compare them, and find more support. "Explain this to my 7-year-old using things she loves" turns the cell data into a story built from the family's own favourites.

## How Qloo is used

| Feature | Qloo API |
|---|---|
| Resolve favourites | `GET /search` (typed) |
| Books on illness and caregiving | `/v2/insights` `filter.type=urn:entity:book`, `filter.tags` (union) + `signal.interests.entities` |
| Podcasts | `/search` for topic candidates → `/v2/insights` with `filter.results.entities` + `signal.interests.entities` to rank by taste |
| A night off | `/v2/insights` for `urn:entity:movie` / `urn:entity:tv_show` from taste signals |
| Places to breathe | `/v2/insights` `urn:entity:place` + `filter.location.query` + category tags + `filter.exclude.tags` |
| "Because you love …" | `feature.explainability=true` |
| Agent tag discovery | `/v2/tags` with semantic search |

## The cell atlas

`data_build/build_atlas.py` compresses the processed pseudobulk data of **Replogle et al., "Mapping information-rich genotype–phenotype landscapes with genome-scale Perturb-seq", *Cell* 2022** (figshare, CC BY 4.0) into `app/atlas.json.gz` (1.6 MB): per knocked-down gene, knockdown efficiency, an energy-test significance flag, effect size and its percentile, mean z-scores of nine curated gene programs, the most up- and down-regulated genes, and nearest neighbours in a 64-dimensional PCA embedding of all knockdown profiles. For K562, the day-7 essential-gene screen is used when it knocked the gene down more strongly than the genome-wide screen.

To rebuild: download `K562_gwps_normalized_bulk_01.h5ad`, `K562_essential_normalized_bulk_01.h5ad` and `rpe1_normalized_bulk_01.h5ad` from the figshare record into `data_build/` (as `K562_gwps.h5ad`, `K562_essential.h5ad`, `rpe1.h5ad`) and run `python build_atlas.py` with `anndata` installed.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export QLOO_API_KEY=...   # hackathon key (https://hackathon.api.qloo.com)
export LLM_API_KEY=...    # Google AI Studio key
.venv/bin/uvicorn app.main:app --reload
```

## Safety

The model is instructed never to predict symptoms, severity, prognosis or treatment, to stick to tool results, and to point families to their care team. Every page carries a disclaimer.

## License

MIT — see [LICENSE](LICENSE). Cell data © Replogle et al. 2022 (CC BY 4.0).
