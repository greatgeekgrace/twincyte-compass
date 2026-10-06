"""Compress Replogle et al. 2022 pseudobulk CRISPRi Perturb-seq into a small JSON atlas."""
import gzip
import json
import re

import anndata as ad
import numpy as np

PROGRAMS = {
    "ribosome": ("Making proteins (ribosomes)", {"re": r"^RP[LS]\d+[A-Z]?\d*$"}),
    "ribosome_biogenesis": ("Building new ribosomes (cell growth)", {"genes": "NPM1 NCL NOP56 NOP58 FBL DKC1 NOP16 RRP9 WDR43 POLR1A POLR1B NOP2 BOP1 PES1 RRS1 NIP7 GNL3 NOLC1 RRP12 UTP20"}),
    "oxphos": ("Energy production (mitochondria)", {"re": r"^(MT-|NDUF|COX\d|UQCR|ATP5|SDH[ABCD]$)"}),
    "cell_cycle": ("Cell division", {"genes": "MKI67 TOP2A CCNB1 CCNB2 CDK1 PLK1 AURKA AURKB BUB1 CENPF E2F1 MCM2 MCM3 MCM4 MCM5 MCM6 MCM7 PCNA TYMS CCNE1 CCNA2 CDC20 UBE2C"}),
    "p53_dna_damage": ("DNA-damage alarm (p53)", {"genes": "CDKN1A MDM2 GDF15 BTG2 SESN1 TP53I3 FAS BBC3 PLK3 RRM2B ZMAT3 TNFRSF10B AEN FDXR SPATA18 TRIAP1"}),
    "stress": ("Cellular stress response", {"genes": "ATF4 DDIT3 ASNS TRIB3 CHAC1 HSPA5 XBP1 HERPUD1 SESN2 PSAT1 PHGDH VEGFA ATF3 PPP1R15A SLC7A11 SEL1L DNAJB9 PDIA4 HYOU1 CEBPB"}),
    "cholesterol": ("Making cholesterol and fats", {"genes": "HMGCR HMGCS1 LDLR INSIG1 SQLE FDFT1 MVD IDI1 SCD FASN DHCR7 LSS CYP51A1 MSMO1 FDPS MVK SC5D NSDHL"}),
    "heat_shock": ("Protein folding helpers", {"genes": "HSPA1A HSPA1B DNAJB1 HSPH1 HSP90AA1 HSPA8 BAG3 HSPD1 HSPE1 CHORDC1 DNAJA1 HSPB1"}),
    "erythroid": ("Red-blood-cell identity (haemoglobin)", {"genes": "HBG1 HBG2 HBZ HBE1 HBA1 HBA2 GYPA GATA1 TAL1 KLF1 ALAS2 TFRC SLC25A37 FECH UROD"}),
}


def load(path):
    a = ad.read_h5ad(path)
    X = np.clip(np.nan_to_num(np.asarray(a.X, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0), -30, 30)
    genes = a.var["gene_name"].astype(str).to_numpy()
    rows = {}
    for i, key in enumerate(a.obs_names):
        target = key.split("_")[1]
        if target.startswith("non-targeting"):
            continue
        ncell = float(a.obs["num_cells_filtered"].iloc[i])
        if target not in rows or ncell > rows[target][1]:
            rows[target] = (i, ncell)
    return a, X, genes, rows


def program_index(genes):
    idx = {}
    for name, (_, p) in PROGRAMS.items():
        if "re" in p:
            sel = [i for i, g in enumerate(genes) if re.match(p["re"], g)]
        else:
            want = set(p["genes"].split())
            sel = [i for i, g in enumerate(genes) if g in want]
        idx[name] = np.array(sel, dtype=int)
    return idx


def profiles(path, source):
    a, X, genes, rows = load(path)
    out = {}
    for t, (i, ncell) in rows.items():
        fold = a.obs["fold_expr"].iloc[i]
        p = a.obs["energy_test_p_value"].iloc[i]
        out[t] = {"z": X[i], "cells": int(ncell), "knockdown": None if np.isnan(fold) else float(1 - fold),
                  "p": None if np.isnan(p) else float(p), "source": source}
    return out, genes


def build(entries, genes, line, top=20):
    pidx = program_index(genes)
    targets = sorted(entries)
    M = np.stack([entries[t]["z"] for t in targets])
    Mc = M - M.mean(0)
    U, S, _ = np.linalg.svd(Mc, full_matrices=False)
    E = U[:, :64] * S[:64]
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    strength = np.sqrt((M ** 2).mean(1))
    out = {}
    for k, t in enumerate(targets):
        z = M[k]
        e = entries[t]
        order = np.argsort(z)
        down = [[genes[j], round(float(z[j]), 2)] for j in order[:top] if z[j] < -0.5 and genes[j] != t]
        up = [[genes[j], round(float(z[j]), 2)] for j in order[::-1][:top] if z[j] > 0.5]
        sims = E @ E[k]
        nn = [[targets[j], round(float(sims[j]), 3)] for j in np.argsort(-sims)[1:9]] if strength[k] > 0.08 else []
        out[t] = {
            "source": e["source"], "cells": e["cells"],
            "knockdown": None if e["knockdown"] is None else round(e["knockdown"], 2),
            "significant": e["p"] is not None and e["p"] < 0.01,
            "strength": round(float(strength[k]), 3),
            "n_changed": int((np.abs(z) > 1).sum()),
            "up": up, "down": down,
            "programs": {n: round(float(z[ix].mean()), 3) for n, ix in pidx.items() if len(ix)},
            "similar": nn,
        }
    pct = np.percentile(strength, [50, 75, 90, 99]).round(3).tolist()
    return {"line": line, "n_measured_genes": int(len(genes)), "strength_pct_50_75_90_99": pct, "perturbations": out}


if __name__ == "__main__":
    gw, g1 = profiles("K562_gwps.h5ad", "K562 genome-wide screen")
    es, g2 = profiles("K562_essential.h5ad", "K562 essential-gene screen (day 7)")
    pos = {g: i for i, g in enumerate(g1)}
    src = np.array([pos.get(g, -1) for g in g2])
    keep = src >= 0
    for e in es.values():
        z = np.zeros(len(g1), dtype=np.float32)
        z[src[keep]] = e["z"][keep]
        e["z"] = z
    print("essential genes mapped into genome-wide space:", int(keep.sum()), "of", len(g2))
    k562 = dict(gw)
    for t, e in es.items():
        if t not in k562 or (e["knockdown"] or 0) > (k562[t]["knockdown"] or 0) + 0.1:
            k562[t] = e
    rp, g3 = profiles("rpe1.h5ad", "RPE1 essential-gene screen (day 7)")
    atlas = {
        "source": "Replogle et al. 2022, Cell — genome-scale CRISPRi Perturb-seq (pseudobulk, z-scored against non-targeting controls)",
        "programs": {n: d for n, (d, _) in PROGRAMS.items()},
        "lines": {
            "K562": build(k562, g1, "K562 — a human blood (erythroleukaemia) cell line"),
            "RPE1": build(rp, g3, "hTERT-RPE1 — a near-normal human retinal cell line"),
        },
    }
    with gzip.open("../app/atlas.json.gz", "wt") as f:
        json.dump(atlas, f, separators=(",", ":"))
    for k, v in atlas["lines"].items():
        print(k, len(v["perturbations"]), v["strength_pct_50_75_90_99"])
