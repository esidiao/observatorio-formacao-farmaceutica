"""
Extrai do Censo 2024 (MICRODADOS_CADASTRO_CURSOS) indicadores de perfil de
acesso e equidade dos cursos de Farmacia, agregados por UF e por municipio
(oferta com localizacao municipal):
  - % mulheres entre ingressantes
  - % pretos, pardos e indigenas entre quem declarou cor/raca
  - % ingressantes com FIES ou PROUNI
  - % vagas noturnas (presencial)
  - % vagas em rede publica
Enriquece nacional.json e data/municipios/*.json.
"""
import pandas as pd, json, sys, unicodedata
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

BASE = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/microdados_censo_da_educacao_superior_2024/dados")
REPO = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio-nacional")

def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()

COLS = ["SG_UF", "CO_MUNICIPIO", "TP_REDE", "QT_VG_TOTAL", "QT_VG_TOTAL_DIURNO",
        "QT_VG_TOTAL_NOTURNO", "QT_ING", "QT_ING_FEM", "QT_ING_BRANCA",
        "QT_ING_PRETA", "QT_ING_PARDA", "QT_ING_AMARELA", "QT_ING_INDIGENA",
        "QT_ING_FIES", "QT_ING_PROUNII", "QT_ING_PROUNIP", "NO_CINE_ROTULO"]

print("[1] Lendo Censo 2024...")
df = pd.read_csv(BASE / "MICRODADOS_CADASTRO_CURSOS_2024.CSV", sep=";", encoding="latin-1",
                 dtype=str, low_memory=False, usecols=lambda c: c in COLS)
df = df[df["NO_CINE_ROTULO"].apply(lambda x: "FARMACIA" in norm(x))].copy()
num = [c for c in COLS if c.startswith("QT_")]
for c in num:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
print(f"    {len(df)} registros de Farmacia")

def indicadores(g):
    ing = g["QT_ING"].sum()
    decl = g[["QT_ING_BRANCA","QT_ING_PRETA","QT_ING_PARDA","QT_ING_AMARELA","QT_ING_INDIGENA"]].sum().sum()
    ppi = g[["QT_ING_PRETA","QT_ING_PARDA","QT_ING_INDIGENA"]].sum().sum()
    fin = g[["QT_ING_FIES","QT_ING_PROUNII","QT_ING_PROUNIP"]].sum().sum()
    vg_pres = g["QT_VG_TOTAL_DIURNO"].sum() + g["QT_VG_TOTAL_NOTURNO"].sum()
    vg_tot = g["QT_VG_TOTAL"].sum()
    vg_pub = g[g["TP_REDE"] == "1"]["QT_VG_TOTAL"].sum()
    pct = lambda a, b: round(float(a) / float(b) * 100, 1) if b > 0 else None
    return {
        "pct_mulheres":       pct(g["QT_ING_FEM"].sum(), ing),
        "pct_ppi":            pct(ppi, decl),
        "pct_financiamento":  pct(fin, ing),
        "pct_noturno":        pct(g["QT_VG_TOTAL_NOTURNO"].sum(), vg_pres),
        "pct_rede_publica":   pct(vg_pub, vg_tot),
    }

uf_perf  = {norm(uf): indicadores(g) for uf, g in df.groupby("SG_UF") if pd.notna(uf)}
mun_perf = {str(c).split(".")[0]: indicadores(g) for c, g in df.groupby("CO_MUNICIPIO") if pd.notna(c)}

# Merge nacional.json
nac = json.load(open(REPO / "data/nacional.json", encoding="utf-8"))
print(f"\n{'UF':4} | {'%mulh':6} | {'%PPI':6} | {'%fin':6} | {'%not':6} | {'%pub':6}")
print("-" * 48)
for uf in sorted(nac["ufs"]):
    r = uf_perf.get(uf)
    if r:
        nac["ufs"][uf].update(r)
        print(f"{uf:4} | {str(r['pct_mulheres']):6} | {str(r['pct_ppi']):6} | {str(r['pct_financiamento']):6} | {str(r['pct_noturno']):6} | {str(r['pct_rede_publica']):6}")
json.dump(nac, open(REPO / "data/nacional.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# Merge municipios/*.json
n_mun = 0
for f in (REPO / "data/municipios").glob("*.json"):
    d = json.load(open(f, encoding="utf-8"))
    ch = False
    for nome, dm in d.items():
        cod = str(dm.get("cod_municipio", "")).split(".")[0]
        if cod in mun_perf:
            dm.update(mun_perf[cod]); ch = True; n_mun += 1
    if ch:
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"\n[OK] {len(uf_perf)} UFs e {n_mun} municipios enriquecidos (perfil de acesso e equidade)")
