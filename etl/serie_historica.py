"""
Serie historica nacional da formacao farmaceutica (Censo INEP, 2015-2024).
Baixa os microdados de cursos de cada ano, filtra Farmacia e agrega totais
nacionais por modalidade. Gera data/serie_historica.json.

ATENCAO ao codigo de modalidade (TP_MODALIDADE_ENSINO):
  - 2015-2023: 1=Presencial, 2=Semipresencial, 3=EaD
  - 2024:      1=Presencial, 2=EaD
"""
import sys, io, json, zipfile, unicodedata, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

REPO = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio-nacional")
SCRATCH = Path("C:/Users/User/AppData/Local/Temp/claude/G--Meu-Drive-Works-CLAUDE-IA/32ed4a02-4992-4a2f-a1f4-f781538e80a6/scratchpad/histcenso")
SCRATCH.mkdir(parents=True, exist_ok=True)
LOCAL_2024 = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/microdados_censo_da_educacao_superior_2024/dados/MICRODADOS_CADASTRO_CURSOS_2024.CSV")

ANOS = list(range(2015, 2025))
# Microdados de cursos usam 1=Presencial, 2=EaD em toda a serie (verificado).
EAD_CODE = lambda ano: 2

def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()

def baixar(ano):
    z = SCRATCH / f"c{ano}.zip"
    if z.exists() and z.stat().st_size > 1_000_000:
        return z
    url = f"https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"
    print(f"  baixando {ano}...", flush=True)
    subprocess.run(["curl", "-s", "-L", "--retry", "3", "--retry-delay", "2",
                    "-A", "Mozilla/5.0", "-o", str(z), url], check=True)
    if not z.exists() or z.stat().st_size < 1_000_000:
        raise RuntimeError(f"download {ano} falhou")
    return z

def ler_cursos_df(ano):
    if ano == 2024 and LOCAL_2024.exists():
        src = LOCAL_2024
        df = pd.read_csv(src, sep=";", encoding="latin-1", dtype=str, low_memory=False)
        return df
    z = baixar(ano)
    zf = zipfile.ZipFile(z)
    nome = next(n for n in zf.namelist() if "CURSO" in n.upper() and n.upper().endswith(".CSV"))
    with zf.open(nome) as f:
        df = pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep=";", dtype=str, low_memory=False)
    return df

def col(df, *cands):
    for c in cands:
        if c in df.columns:
            return c
    return None

serie = []
for ano in ANOS:
    print(f"[{ano}] processando...", flush=True)
    df = ler_cursos_df(ano)
    c_curso = col(df, "NO_CINE_ROTULO", "NO_CURSO", "NO_CURSO_CINE")
    farm = df[df[c_curso].apply(lambda x: "FARMACIA" in norm(x))].copy()
    c_vg = col(farm, "QT_VG_TOTAL", "QT_VAGAS_AUTORIZADAS")
    c_mod = col(farm, "TP_MODALIDADE_ENSINO")
    c_mat = col(farm, "QT_MAT", "QT_MATRICULA")
    c_ing = col(farm, "QT_ING", "QT_INGRESSO")
    c_conc = col(farm, "QT_CONC", "QT_CONCLUINTE")
    for c in [c_vg, c_mod, c_mat, c_ing, c_conc]:
        if c:
            farm[c] = pd.to_numeric(farm[c], errors="coerce").fillna(0)
    ead = EAD_CODE(ano)
    vg = farm[c_vg]
    pres_mask = farm[c_mod] == 1
    ead_mask = farm[c_mod] == ead
    reg = {
        "ano": ano,
        "n_cursos": int((farm[c_vg] > 0).sum()),
        "vagas_total": int(vg.sum()),
        "vagas_presencial": int(vg[pres_mask].sum()),
        "vagas_ead": int(vg[ead_mask].sum()),
        "matriculas": int(farm[c_mat].sum()) if c_mat else None,
        "ingressos": int(farm[c_ing].sum()) if c_ing else None,
        "concluintes": int(farm[c_conc].sum()) if c_conc else None,
    }
    reg["pct_ead"] = round(reg["vagas_ead"] / reg["vagas_total"] * 100, 1) if reg["vagas_total"] else 0
    serie.append(reg)
    print(f"    vagas={reg['vagas_total']:,} (EaD {reg['pct_ead']}%) | matric={reg['matriculas']:,} | conc={reg['concluintes']:,}")

out = {
    "series": [r["ano"] for r in serie],
    "nacional": serie,
    "fonte": "INEP — Microdados do Censo da Educação Superior (2015–2024)",
    "nota_modalidade": "EaD = TP_MODALIDADE 3 (2015–2023) e 2 (2024); presencial = 1. Vagas EaD registradas na sede.",
}
json.dump(out, open(REPO / "data/serie_historica.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n[OK] data/serie_historica.json com {len(serie)} anos")
