"""
Serie historica nacional da formacao farmaceutica (Censo INEP, 2015-2025).
Baixa os microdados de cursos de cada ano, filtra Farmacia e agrega totais
nacionais por modalidade. Gera data/serie_historica.json.

Para acrescentar so a edicao 2025 sem rebaixar as demais (que ja estao no JSON),
aponte o arquivo gerado por etl/censo2025_adaptador.py:

    python etl/serie_historica.py --so-ano 2025 --csv <dir>/MICRODADOS_CADASTRO_CURSOS_2025.CSV

ATENCAO ao codigo de modalidade (TP_MODALIDADE_ENSINO):
  - 2015-2024: 1=Presencial, 2=EaD (so existem estes dois codigos; conferido ano a ano)
  - 2025+:     1=Presencial, 2=EaD, 3=SEMIPRESENCIAL (Decreto 12.456/2025). O 3 deixou
               de ser EaD: nao reaproveitar o codigo da serie antiga.
"""
import sys, io, json, zipfile, unicodedata, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path("C:/Users/User/AppData/Local/Temp/claude/G--Meu-Drive-Works-CLAUDE-IA/32ed4a02-4992-4a2f-a1f4-f781538e80a6/scratchpad/histcenso")
SCRATCH.mkdir(parents=True, exist_ok=True)
LOCAL_2024 = Path("G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/microdados_censo_da_educacao_superior_2024/dados/MICRODADOS_CADASTRO_CURSOS_2024.CSV")

ANOS = list(range(2015, 2025))   # 2025 entra por --so-ano (layout novo do INEP)
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

def registro(farm, ano):
    """Totais nacionais de um ano a partir das linhas de Farmacia."""
    c_vg = col(farm, "QT_VG_TOTAL", "QT_VAGAS_AUTORIZADAS")
    c_mod = col(farm, "TP_MODALIDADE_ENSINO")
    c_mat = col(farm, "QT_MAT", "QT_MATRICULA")
    c_ing = col(farm, "QT_ING", "QT_INGRESSO")
    c_conc = col(farm, "QT_CONC", "QT_CONCLUINTE")
    for c in [c_vg, c_mod, c_mat, c_ing, c_conc]:
        if c:
            farm[c] = pd.to_numeric(farm[c], errors="coerce").fillna(0)
    ead = EAD_CODE(ano)
    # SITUACAO DO CURSO: coluna que so existe de 2025 em diante.
    #
    # Sem ela esta serie somava na capacidade os cursos que a regulacao
    # encerrou, e o resultado foi uma divergencia de 489.801 contra 174.793
    # vagas entre a serie nacional e a soma das UFs em 2025 — a diferenca eram,
    # integralmente, cursos em extincao. A ausencia da coluna vira "tudo em
    # atividade", que e o que as edicoes anteriores significavam: elas nao
    # distinguiam situacao.
    c_sit = col(farm, "TP_SITUACAO")
    if c_sit:
        ativo = farm[c_sit].astype(str).str.strip().replace("", "1") == "1"
    else:
        ativo = farm[c_vg].notna()      # tudo, nas edicoes sem a coluna
    vg = farm[c_vg].where(ativo, 0)
    vg_extin = farm[c_vg].where(~ativo, 0)
    pres_mask = farm[c_mod] == 1
    ead_mask = farm[c_mod] == ead
    reg = {
        "ano": ano,
        # Curso com vaga EM ATIVIDADE. Curso em extincao continua existindo e
        # aparece em `cursos_em_extincao`, nao aqui.
        "n_cursos": int(((farm[c_vg] > 0) & ativo).sum()),
        "vagas_total": int(vg.sum()),
        "vagas_presencial": int(vg[pres_mask].sum()),
        "vagas_ead": int(vg[ead_mask].sum()),
        "matriculas": int(farm[c_mat].sum()) if c_mat else None,
        "ingressos": int(farm[c_ing].sum()) if c_ing else None,
        "concluintes": int(farm[c_conc].sum()) if c_conc else None,
    }
    if ano >= 2025:
        semi = int(vg[farm[c_mod] == 3].sum())
        reg["vagas_semipresencial"] = semi
        # Fora da capacidade ativa, publicada ao lado: nao desaparece.
        reg["vagas_em_extincao"] = int(vg_extin.sum())
        reg["cursos_em_extincao"] = int(((farm[c_vg] > 0) & ~ativo).sum())
        # Guarda: toda vaga ATIVA tem de cair em alguma modalidade conhecida.
        resto = reg["vagas_total"] - reg["vagas_presencial"] - reg["vagas_ead"] - semi
        if resto:
            sys.exit(f"[ABORTADO] {resto} vagas fora de presencial/EaD/semipresencial em {ano}.")
    reg["pct_ead"] = round(reg["vagas_ead"] / reg["vagas_total"] * 100, 1) if reg["vagas_total"] else 0
    return reg


def so_ano(ano, csv):
    """Acrescenta/substitui UM ano no serie_historica.json ja existente."""
    caminho = REPO / "data/serie_historica.json"
    out = json.load(open(caminho, encoding="utf-8"))
    df = pd.read_csv(csv, sep=";", encoding="latin-1", dtype=str, low_memory=False)
    c_curso = col(df, "NO_CINE_ROTULO", "NO_CURSO", "NO_CURSO_CINE")
    farm = df[df[c_curso].apply(lambda x: "FARMACIA" in norm(x))].copy()
    reg = registro(farm, ano)
    out["nacional"] = [r for r in out["nacional"] if r["ano"] != ano] + [reg]
    out["nacional"].sort(key=lambda r: r["ano"])
    out["series"] = [r["ano"] for r in out["nacional"]]
    out["fonte"] = f"INEP — Microdados do Censo da Educação Superior ({out['series'][0]}–{out['series'][-1]})"
    out["nota_modalidade"] = ("EaD = TP_MODALIDADE 2 em toda a série (2015–2025); presencial = 1; "
                              "a partir de 2025 o 3 é semipresencial (campo vagas_semipresencial, "
                              "incluído em vagas_total). Vagas EaD registradas na sede. A mudança de "
                              "definição em 2025 (Decreto 12.456/2025) limita a comparação da "
                              "participação da EaD com os anos anteriores.")
    json.dump(out, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[OK] {ano}: {reg}")


if "--so-ano" in sys.argv:
    _ano = int(sys.argv[sys.argv.index("--so-ano") + 1])
    _csv = sys.argv[sys.argv.index("--csv") + 1]
    so_ano(_ano, _csv)
    sys.exit(0)

serie = []
for ano in ANOS:
    print(f"[{ano}] processando...", flush=True)
    df = ler_cursos_df(ano)
    c_curso = col(df, "NO_CINE_ROTULO", "NO_CURSO", "NO_CURSO_CINE")
    farm = df[df[c_curso].apply(lambda x: "FARMACIA" in norm(x))].copy()
    reg = registro(farm, ano)
    serie.append(reg)
    print(f"    vagas={reg['vagas_total']:,} (EaD {reg['pct_ead']}%) | matric={reg['matriculas']:,} | conc={reg['concluintes']:,}")

out = {
    "series": [r["ano"] for r in serie],
    "nacional": serie,
    "fonte": "INEP — Microdados do Censo da Educação Superior (2015–2024)",
    "nota_modalidade": "EaD = TP_MODALIDADE 2 em toda a série; presencial = 1. Vagas EaD registradas na sede.",
}
json.dump(out, open(REPO / "data/serie_historica.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n[OK] data/serie_historica.json com {len(serie)} anos")
