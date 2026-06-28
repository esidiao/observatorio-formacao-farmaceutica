"""
Separa por MODALIDADE (presencial x EaD) os indicadores de qualidade dos cursos
de Farmacia (CPC 2023), e mapeia a capacidade (vagas/cursos) ja existente.
Grava nacional.json['ufs'][UF]['por_modalidade'] = {presencial:{...}, ead:{...}}.
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

c_area = find("AREA", "AVALIACAO"); c_uf = find("SIGLA", "UF")
c_mod = find("MODALIDADE"); c_conc = find("CONCLUINTES", "PARTICIPANTES")
MAP = {  # campo no site -> coluna CPC
    "IDD":               find("NOTA PADRONIZADA", "IDD"),
    "CC":                find("CONCEITO ENADE", "CONTINUO"),
    "CPC_cont":          find("CPC", "CONTINUO"),
    "pct_doc_doutores":  find("NOTA BRUTA", "DOUTORES"),
    "pct_doc_mestres":   find("NOTA BRUTA", "MESTRES"),
    "pct_doc_regime":    find("NOTA BRUTA", "REGIME"),
    "cpc_org_didatico":  find("NOTA BRUTA", "DIDATICO"),
    "cpc_infraestrutura":find("NOTA BRUTA", "INFRAESTRUTURA"),
    "cpc_oportunidade":  find("NOTA BRUTA", "OPORTUNIDADE"),
}
PCT = {"pct_doc_doutores", "pct_doc_mestres", "pct_doc_regime"}  # *100

df = raw[[c_area, c_uf, c_mod, c_conc] + list(MAP.values())].copy()
df.columns = ["area", "uf", "mod", "conc"] + list(MAP.keys())
df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))].copy()
for col in ["conc"] + list(MAP.keys()):
    df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
df["conc"] = df["conc"].fillna(0)
df["_mod"] = df["mod"].apply(lambda x: "ead" if "DIST" in norm(x) else "presencial")

def pond(g, col, pct=False):
    sub = g.dropna(subset=[col])
    if not len(sub):
        return None
    w = sub["conc"]; m = (sub[col] * w).sum() / w.sum() if w.sum() > 0 else sub[col].mean()
    return round(float(m) * (100 if pct else 1), 1 if pct else 2)

split = {}  # uf -> {presencial:{...}, ead:{...}}
for (uf, mod), g in df.groupby(["uf", "_mod"]):
    split.setdefault(norm(uf), {}).setdefault(mod, {})
    for key in MAP:
        split[norm(uf)][mod][key] = pond(g, key, key in PCT)
    split[norm(uf)][mod]["n_cursos"] = int(len(g))

# Merge + mapeia capacidade (vagas) ja existente
nac = json.load(open(REPO / "data/nacional.json", encoding="utf-8"))
for uf, d in nac["ufs"].items():
    pm = split.get(uf, {})
    pres = pm.get("presencial", {}).copy()
    ead = pm.get("ead", {}).copy()
    # capacidade por modalidade (cobertura total, vinda do Censo)
    pres["vagas_total_real"] = d.get("vagas_presencial")
    ead["vagas_total_real"]  = d.get("vagas_ead")
    pres["n_cursos"] = d.get("n_cursos_presencial", pres.get("n_cursos"))
    ead["n_cursos"]  = d.get("n_cursos_ead", ead.get("n_cursos"))
    d["por_modalidade"] = {"presencial": pres, "ead": ead}

json.dump(nac, open(REPO / "data/nacional.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

n_ead = sum(1 for uf in nac["ufs"].values() if uf["por_modalidade"]["ead"].get("IDD") is not None)
print(f"[OK] por_modalidade gravado nas 27 UFs. {n_ead} UFs com qualidade EaD avaliada.")
print("\nExemplo SP:")
print(json.dumps(nac["ufs"]["SP"]["por_modalidade"], ensure_ascii=False, indent=1))
