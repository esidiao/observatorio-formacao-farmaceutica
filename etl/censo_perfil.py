"""
Extrai do Censo (MICRODADOS_CADASTRO_CURSOS_AAAA) indicadores de perfil de
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

# Caminhos resolvidos em tempo de execucao. Ate 2026-07-26 estes scripts fixavam
# REPO em "G:/Meu Drive/.../observatorio-nacional" — pasta que deixou de existir
# quando o repositorio saiu do Google Drive, o que os deixou quebrados e os campos
# que produzem sem forma de serem regenerados.
REPO = Path(__file__).resolve().parent.parent


def _fonte_externa(variavel, padrao):
    """Caminho de fonte externa nao versionada: variavel de ambiente > padrao."""
    import os
    return Path(os.environ.get(variavel, padrao))

import os
ANO_CENSO = os.environ.get("OBS_CENSO_ANO", "2025")
BASE = _fonte_externa("OBS_CENSO_DIR", "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2025/legado_farmacia")

def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()

COLS = ["SG_UF", "CO_MUNICIPIO", "TP_REDE", "QT_VG_TOTAL", "QT_VG_TOTAL_DIURNO",
        "QT_VG_TOTAL_NOTURNO", "QT_ING", "QT_ING_FEM", "QT_ING_BRANCA",
        "QT_ING_PRETA", "QT_ING_PARDA", "QT_ING_AMARELA", "QT_ING_INDIGENA",
        "QT_ING_FIES", "QT_ING_PROUNII", "QT_ING_PROUNIP", "NO_CINE_ROTULO"]

print(f"[1] Lendo Censo {ANO_CENSO}...")
df = pd.read_csv(BASE / f"MICRODADOS_CADASTRO_CURSOS_{ANO_CENSO}.CSV", sep=";", encoding="latin-1",
                 dtype=str, low_memory=False, usecols=lambda c: c in COLS)
df = df[df["NO_CINE_ROTULO"].apply(lambda x: "FARMACIA" in norm(x))].copy()
num = [c for c in COLS if c.startswith("QT_")]
for c in num:
    df[c] = pd.to_numeric(df[c], errors="coerce")   # NaN = suprimido/ausente, NUNCA 0
# Vagas e ingressantes totais nunca sao suprimidos; so os RECORTES (sexo, cor,
# financiamento) o sao, e a partir de 2025 isso atinge praticamente todas as
# linhas de polo EaD. Contar "suprimido" como zero subestimaria o numerador e
# deixaria o denominador inteiro (medido: % mulheres cairia de ~15 a ~65 conforme
# o tratamento). Por isso o perfil usa so as linhas com o recorte DIVULGADO.
RECORTES = ["QT_ING_FEM", "QT_ING_BRANCA", "QT_ING_PRETA", "QT_ING_PARDA",
            "QT_ING_AMARELA", "QT_ING_INDIGENA", "QT_ING_FIES", "QT_ING_PROUNII",
            "QT_ING_PROUNIP"]
for c in [x for x in num if x not in RECORTES]:
    df[c] = df[c].fillna(0)
print(f"    {len(df)} registros de Farmacia")

def _divulgado(g, cols):
    """Linhas em que TODAS as colunas do recorte foram divulgadas (nao suprimidas)."""
    return g[g[cols].notna().all(axis=1)]


def indicadores(g):
    # Cada percentual tem numerador e denominador sobre as MESMAS linhas.
    sexo = _divulgado(g, ["QT_ING_FEM"])
    cor_cols = ["QT_ING_BRANCA","QT_ING_PRETA","QT_ING_PARDA","QT_ING_AMARELA","QT_ING_INDIGENA"]
    cor = _divulgado(g, cor_cols)
    fin_cols = ["QT_ING_FIES","QT_ING_PROUNII","QT_ING_PROUNIP"]
    finr = _divulgado(g, fin_cols)
    ing = g["QT_ING"].sum()
    decl = cor[cor_cols].sum().sum()
    ppi = cor[["QT_ING_PRETA","QT_ING_PARDA","QT_ING_INDIGENA"]].sum().sum()
    fin = finr[fin_cols].sum().sum()
    vg_pres = g["QT_VG_TOTAL_DIURNO"].sum() + g["QT_VG_TOTAL_NOTURNO"].sum()
    vg_tot = g["QT_VG_TOTAL"].sum()
    vg_pub = g[g["TP_REDE"] == "1"]["QT_VG_TOTAL"].sum()
    pct = lambda a, b: round(float(a) / float(b) * 100, 1) if b > 0 else None
    return {
        "pct_mulheres":       pct(sexo["QT_ING_FEM"].sum(), sexo["QT_ING"].sum()),
        "pct_ppi":            pct(ppi, decl),
        "pct_financiamento":  pct(fin, finr["QT_ING"].sum()),
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
