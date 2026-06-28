"""
Extrai do CPC_2023.xlsx (INEP) as proporcoes reais de qualificacao docente dos
cursos de Farmacia: % mestres (ou mais), % doutores, % regime integral/parcial.
Calcula media ponderada por concluintes participantes, por UF e por municipio.
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

print("[1] Lendo CPC_2023.xlsx...")
raw = pd.read_excel(XLSX, sheet_name="CPC_2023", header=0, dtype=str)
cols = {norm(c): c for c in raw.columns}
def find(*subs):
    for k, v in cols.items():
        if all(s in k for s in subs):
            return v
    return None

c_area = find("AREA", "AVALIACAO")
c_uf   = find("SIGLA", "UF")
c_mun  = find("CODIGO", "MUNICIPIO")
c_conc = find("CONCLUINTES", "PARTICIPANTES")
c_mes  = find("NOTA BRUTA", "MESTRES")
c_dou  = find("NOTA BRUTA", "DOUTORES")
c_reg  = find("NOTA BRUTA", "REGIME")
print(f"    cols: uf={c_uf!r} mun={c_mun!r} mestres={c_mes!r} doutores={c_dou!r} regime={c_reg!r}")

df = raw[[c_area, c_uf, c_mun, c_conc, c_mes, c_dou, c_reg]].copy()
df.columns = ["area", "uf", "cod_mun", "conc", "mes", "dou", "reg"]
df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))].copy()
for col in ["conc", "mes", "dou", "reg"]:
    df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")
df["conc"] = df["conc"].fillna(0)
print(f"    {len(df)} cursos de Farmacia avaliados")

def pond(g, col):
    sub = g.dropna(subset=[col])
    if not len(sub):
        return None
    w = sub["conc"]
    if w.sum() > 0:
        return round(float((sub[col] * w).sum() / w.sum()) * 100, 1)
    return round(float(sub[col].mean()) * 100, 1)

# ---- Por UF ----
uf_doc = {}
for uf, g in df.groupby("uf"):
    uf_doc[norm(uf)] = {
        "pct_doc_mestres": pond(g, "mes"),
        "pct_doc_doutores": pond(g, "dou"),
        "pct_doc_regime": pond(g, "reg"),
        "n_cursos_docente": int(len(g)),
    }

# ---- Por municipio (codigo IBGE) ----
mun_doc = {}
for cod, g in df.groupby("cod_mun"):
    cod = str(cod).split(".")[0]
    mun_doc[cod] = {
        "pct_doc_mestres": pond(g, "mes"),
        "pct_doc_doutores": pond(g, "dou"),
        "pct_doc_regime": pond(g, "reg"),
    }

# ---- Merge nacional.json ----
nac = json.load(open(REPO / "data/nacional.json", encoding="utf-8"))
print(f"\n{'UF':4} | {'%mestres':8} | {'%doutores':9} | {'%regime':7} | n")
print("-" * 45)
for uf in sorted(nac["ufs"]):
    r = uf_doc.get(uf)
    if r:
        nac["ufs"][uf].update(r)
        print(f"{uf:4} | {str(r['pct_doc_mestres']):8} | {str(r['pct_doc_doutores']):9} | {str(r['pct_doc_regime']):7} | {r['n_cursos_docente']}")
json.dump(nac, open(REPO / "data/nacional.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ---- Merge municipios/*.json (por cod_municipio) ----
n_mun_upd = 0
mun_dir = REPO / "data/municipios"
for f in mun_dir.glob("*.json"):
    d = json.load(open(f, encoding="utf-8"))
    changed = False
    for nome, dm in d.items():
        cod = str(dm.get("cod_municipio", "")).split(".")[0]
        if cod in mun_doc:
            dm.update(mun_doc[cod])
            changed = True
            n_mun_upd += 1
    if changed:
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"\n[OK] {len([u for u in uf_doc])} UFs e {n_mun_upd} municipios enriquecidos com qualificacao docente")
nat_m = [v['pct_doc_mestres'] for v in uf_doc.values() if v['pct_doc_mestres'] is not None]
nat_d = [v['pct_doc_doutores'] for v in uf_doc.values() if v['pct_doc_doutores'] is not None]
print(f"     Media nacional (simples das UFs): mestres {sum(nat_m)/len(nat_m):.1f}% | doutores {sum(nat_d)/len(nat_d):.1f}%")
