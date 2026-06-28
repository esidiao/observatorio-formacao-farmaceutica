"""
Extrai do CPC_2023.xlsx (INEP) as dimensões avaliadas pelos estudantes nos cursos
de Farmácia (escala 1–6, Nota Bruta): Organização Didático-Pedagógica,
Infraestrutura e Instalações Físicas, e Oportunidade de Ampliação da Formação.
Média ponderada por concluintes participantes, por UF e por município.
Enriquece nacional.json e data/municipios/*.json.
"""
import pandas as pd, json, sys, unicodedata
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

XLSX = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/CPC_2023.xlsx")
REPO = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio-nacional")

def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()

raw = pd.read_excel(XLSX, sheet_name="CPC_2023", header=0, dtype=str)
cols = {norm(c): c for c in raw.columns}
def find(*subs):
    for k, v in cols.items():
        if all(s in k for s in subs):
            return v

c_area = find("AREA", "AVALIACAO")
c_uf   = find("SIGLA", "UF")
c_mun  = find("CODIGO", "MUNICIPIO")
c_conc = find("CONCLUINTES", "PARTICIPANTES")
DIMS = {
    "cpc_org_didatico":   find("NOTA BRUTA", "DIDATICO"),
    "cpc_infraestrutura": find("NOTA BRUTA", "INFRAESTRUTURA"),
    "cpc_oportunidade":   find("NOTA BRUTA", "OPORTUNIDADE"),
}
print("[1] Colunas:", {k: (v.strip() if v else None) for k, v in DIMS.items()})

df = raw[[c_area, c_uf, c_mun, c_conc] + list(DIMS.values())].copy()
df.columns = ["area", "uf", "cod_mun", "conc"] + list(DIMS.keys())
df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))].copy()
for col in ["conc"] + list(DIMS.keys()):
    df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
df["conc"] = df["conc"].fillna(0)
print(f"    {len(df)} cursos de Farmácia")

def pond(g, col):
    sub = g.dropna(subset=[col])
    if not len(sub):
        return None
    w = sub["conc"]
    if w.sum() > 0:
        return round(float((sub[col] * w).sum() / w.sum()), 2)
    return round(float(sub[col].mean()), 2)

# Por UF
uf_dim = {norm(uf): {k: pond(g, k) for k in DIMS} for uf, g in df.groupby("uf")}
# Por município
mun_dim = {str(c).split(".")[0]: {k: pond(g, k) for k in DIMS} for c, g in df.groupby("cod_mun")}

# Merge nacional.json
nac = json.load(open(REPO / "data/nacional.json", encoding="utf-8"))
print(f"\n{'UF':4} | {'OrgDidat':8} | {'Infra':6} | {'Oportun':7}")
print("-" * 35)
for uf in sorted(nac["ufs"]):
    r = uf_dim.get(uf)
    if r:
        nac["ufs"][uf].update(r)
        print(f"{uf:4} | {str(r['cpc_org_didatico']):8} | {str(r['cpc_infraestrutura']):6} | {str(r['cpc_oportunidade']):7}")
json.dump(nac, open(REPO / "data/nacional.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# Merge municipios/*.json
n_mun = 0
for f in (REPO / "data/municipios").glob("*.json"):
    d = json.load(open(f, encoding="utf-8"))
    ch = False
    for nome, dm in d.items():
        cod = str(dm.get("cod_municipio", "")).split(".")[0]
        if cod in mun_dim:
            dm.update(mun_dim[cod]); ch = True; n_mun += 1
    if ch:
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"\n[OK] {len(uf_dim)} UFs e {n_mun} municípios enriquecidos (org. didático, infraestrutura, oportunidade)")
