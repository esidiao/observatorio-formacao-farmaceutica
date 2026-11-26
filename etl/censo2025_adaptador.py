"""
etl/censo2025_adaptador.py
Reconstroi, a partir dos microdados "tabulados" do Censo 2025, o layout que o ETL
deste repositorio consome desde 2023 (MICRODADOS_CADASTRO_CURSOS_AAAA.CSV e
MICRODADOS_ED_SUP_IES_AAAA.CSV).

Uso:
    python etl/censo2025_adaptador.py --origem <dir 'dados' do Censo 2025> \
        --saida <dir> --rotulo FARMACIA

Por que existe: a partir da edicao 2025 o INEP substituiu os dois arquivos
tradicionais por SETE tabelas (ies, curso, local_oferta, aluno, docente,
biblioteca, laboratorio), com nomes de coluna novos (QT_VG_TOTAL -> QT_VAGA_TOTAL,
QT_MAT -> QT_MATRICULA_TOTAL, SG_UF -> SG_UF_LO...) e sem a camada de polos EaD
na tabela de cursos. Reescrever cada script do ETL arriscaria divergir em silencio
da serie 2015-2024; em vez disso este modulo traduz UMA vez e verifica a traducao.

Como as camadas do 2024 sao reconstruidas (conferido no proprio 2024: sede EaD
tem vagas e nenhuma matricula; polo tem matriculas e nenhuma vaga):

    TP_DIMENSAO 1  curso presencial          <- tabela_curso (modalidade 1) + tabela_aluno nivel 2
    TP_DIMENSAO 3  sede de curso EaD/semi    <- tabela_curso (modalidades 2 e 3); sem UF; so vagas
    TP_DIMENSAO 2  polo (local de oferta)    <- tabela_aluno nivel 3 (modalidades 2 e 3); so alunos
    TP_DIMENSAO 4  polo sem UF (exterior)    <- idem, sem UF

Tres armadilhas da fonte, todas tratadas e verificadas aqui:

 1. SEPARADOR DE MILHAR DENTRO DA CELULA. Em colunas de recorte (QT_ING_FEM,
    QT_MAT_BRANCA...) valores >= 1000 vem como "9.731". Lido como numero vira
    9,731 e quebra qualquer percentual sem erro nenhum. Conferencia: FEM + MASC
    tem de ser igual a QT_ING em toda linha de curso.
 2. SUPRESSAO. No nivel de local de oferta o INEP suprime ("-") celulas com 3 ou
    menos ocorrencias. Nos polos EaD isso atinge praticamente todos os recortes
    de perfil, entao eles ficam NaN (nunca 0) e o perfil por UF so e confiavel
    para a oferta presencial. Totais (QT_ING, QT_MAT, QT_CONC) nao sao suprimidos.
 3. MODALIDADE. Ate 2024, TP_MODALIDADE_ENSINO era a modalidade do curso (1=presencial,
    2=EaD). Em 2025 passa a ser o FORMATO DE OFERTA do Decreto 12.456/2025, com a
    categoria nova 3=Semipresencial. Em 2015-2024 so existiram os codigos 1 e 2
    (conferido em cada Censo); quem assumir que o 3 e EaD, ou que e ignoravel,
    perde ou reclassifica silenciosamente as vagas semipresenciais.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependencias: pip install pandas")

ARQ = {
    "curso": "ces2025_microdados_tabela_curso.csv",
    "ies": "ces2025_microdados_tabela_ies.csv",
    "aluno": "ces2025_microdados_tabela_aluno.csv",
}

# Colunas de identificacao do layout legado, na ordem em que o ETL as espera.
GEO_LEGADO = ["NO_REGIAO", "CO_REGIAO", "NO_UF", "SG_UF", "CO_UF",
              "NO_MUNICIPIO", "CO_MUNICIPIO", "IN_CAPITAL"]
GEO_LO = ["NO_REGIAO_LO", "CO_REGIAO_LO", "NO_UF_LO", "SG_UF_LO", "CO_UF_LO",
          "NO_MUNICIPIO_LO", "CO_MUNICIPIO_LO", "IN_CAPITAL_LO"]
IDENT = ["NU_ANO_CENSO", "TP_ORGANIZACAO_ACADEMICA", "TP_REDE",
         "TP_CATEGORIA_ADMINISTRATIVA", "IN_COMUNITARIA", "IN_CONFESSIONAL",
         "CO_IES", "NO_CURSO", "CO_CURSO", "NO_CINE_ROTULO", "CO_CINE_ROTULO",
         "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL", "CO_CINE_AREA_ESPECIFICA",
         "NO_CINE_AREA_ESPECIFICA", "CO_CINE_AREA_DETALHADA",
         "NO_CINE_AREA_DETALHADA", "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO",
         "TP_NIVEL_ACADEMICO"]
# Quantidades da tabela de cursos, com o nome que o ETL conhece.
VAGAS = {"QT_VAGA_TOTAL": "QT_VG_TOTAL",
         "QT_VAGAS_TOTAL_DIURNO": "QT_VG_TOTAL_DIURNO",
         "QT_VAGAS_TOTAL_NOTURNO": "QT_VG_TOTAL_NOTURNO",
         "QT_VAGAS_TOTAL_EAD": "QT_VG_TOTAL_EAD",
         "QT_VAGAS_TOTAL_SEMI_PRES": "QT_VG_TOTAL_SEMI_PRES",
         "QT_INSCRITO_TOTAL": "QT_INSCRITO_TOTAL"}

_MILHAR = re.compile(r"^\d{1,3}(\.\d{3})+$")
_INTEIRO = re.compile(r"^\d+$")


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def contagem(serie, nome=""):
    """
    Converte uma coluna de contagem do INEP em numero, sem adivinhar.

    "-"/vazio  -> NaN (suprimido ou ausente; JAMAIS 0)
    "9.731"    -> 9731 (separador de milhar dentro da celula)
    "928"      -> 928
    qualquer outra coisa -> ValueError, porque um formato novo nao pode virar
    numero silenciosamente.
    """
    s = serie.astype("string").str.strip()
    vazio = s.isna() | s.isin(["-", ""])
    milhar = s.str.fullmatch(_MILHAR.pattern).fillna(False)
    inteiro = s.str.fullmatch(_INTEIRO.pattern).fillna(False)
    estranho = ~(vazio | milhar | inteiro)
    if estranho.any():
        raise ValueError(f"{nome}: formato de contagem desconhecido: "
                         f"{s[estranho].unique()[:5].tolist()}")
    limpo = s.where(~milhar, s.str.replace(".", "", regex=False))
    return pd.to_numeric(limpo.where(~vazio), errors="raise")


def ler_curso(origem, rotulo):
    df = pd.read_csv(Path(origem) / ARQ["curso"], sep=";", encoding="utf-8-sig",
                     dtype=str, low_memory=False)
    if rotulo:
        alvo = norm(rotulo)
        df = df[df["NO_CINE_ROTULO"].apply(norm).str.contains(alvo, na=False)].copy()
    if df.empty:
        sys.exit(f"[ERRO] Nenhum curso com rotulo CINE contendo '{rotulo}'. Layout mudou?")
    if df["CO_CURSO"].duplicated().any():
        sys.exit("[ERRO] CO_CURSO repetido na tabela de cursos: o adaptador assume "
                 "uma linha por curso (verificado em 2025).")
    return df


def ler_aluno(origem, codigos):
    partes = []
    for bloco in pd.read_csv(Path(origem) / ARQ["aluno"], sep=";", encoding="utf-8-sig",
                             dtype=str, chunksize=100_000, low_memory=False):
        partes.append(bloco[bloco["CO_CURSO"].isin(codigos)])
    if not partes:
        sys.exit("[ERRO] tabela_aluno vazia para os cursos selecionados.")
    return pd.concat(partes, ignore_index=True)


def colunas_qt(df):
    return [c for c in df.columns if c.startswith(("QT_ING", "QT_MAT", "QT_CONC",
                                                   "QT_ALUNO", "QT_SIT"))]


def montar(origem, rotulo, rel=print):
    """Devolve (cursos_legado, ies_legado) e imprime a conferencia."""
    curso = ler_curso(origem, rotulo)
    codigos = set(curso["CO_CURSO"])
    aluno = ler_aluno(origem, codigos)
    qts = colunas_qt(aluno)
    for c in qts:
        aluno[c] = contagem(aluno[c], c)
    for c in list(VAGAS) + ["QT_CURSO", "QT_MATRICULA_TOTAL", "QT_CONCLUINTE_TOTAL",
                            "QT_INGRESSO_TOTAL"]:
        curso[c] = contagem(curso[c], c)

    n2 = aluno[aluno["TP_NIVEL_AGREGACAO"] == "2"].set_index("CO_CURSO")
    n3 = aluno[aluno["TP_NIVEL_AGREGACAO"] == "3"].copy()
    falhas = []

    # ── Conferencias contra a propria fonte ────────────────────────────────────
    if set(n2.index) != codigos:
        falhas.append(f"{len(codigos - set(n2.index))} curso(s) sem linha de nivel 2 em tabela_aluno")
    cj = curso.set_index("CO_CURSO")
    for col_a, col_c, nome in (("QT_MAT", "QT_MATRICULA_TOTAL", "matriculas"),
                               ("QT_CONC", "QT_CONCLUINTE_TOTAL", "concluintes"),
                               ("QT_ING", "QT_INGRESSO_TOTAL", "ingressantes")):
        dif = (n2[col_a].reindex(cj.index) - cj[col_c]).abs().fillna(0)
        if (dif > 0).any():
            falhas.append(f"{nome}: tabela_curso x tabela_aluno divergem em "
                          f"{int((dif > 0).sum())} curso(s) (soma abs {int(dif.sum())})")
    if {"QT_ING_FEM", "QT_ING_MASC"} <= set(n2.columns):
        d = (n2["QT_ING_FEM"] + n2["QT_ING_MASC"] - n2["QT_ING"]).abs()
        if (d > 0).any():
            falhas.append(f"FEM+MASC != ING em {int((d > 0).sum())} curso(s) "
                          f"(separador de milhar nao resolvido?)")
    # Polos: matriculas por local de oferta nunca podem superar o total do curso.
    for mod in ("2", "3"):
        s3 = n3[n3["TP_MODALIDADE_ENSINO"] == mod]["QT_MAT"].sum()
        s2 = n2[n2["TP_MODALIDADE_ENSINO"] == mod]["QT_MAT"].sum()
        if s3 > s2:
            falhas.append(f"modalidade {mod}: polos somam {int(s3)} > cursos {int(s2)}")
        elif s3 < s2:
            rel(f"[AVISO] modalidade {mod}: polos somam {int(s3)} de {int(s2)} "
                f"matriculas (diferenca {int(s2 - s3)}, supressao do INEP).")

    meta = curso[IDENT[1:2] + ["TP_REDE", "TP_CATEGORIA_ADMINISTRATIVA", "IN_COMUNITARIA",
                              "IN_CONFESSIONAL", "CO_IES", "NO_CURSO", "CO_CURSO",
                              "NO_CINE_ROTULO", "CO_CINE_ROTULO", "CO_CINE_AREA_GERAL",
                              "NO_CINE_AREA_GERAL", "CO_CINE_AREA_ESPECIFICA",
                              "NO_CINE_AREA_ESPECIFICA", "CO_CINE_AREA_DETALHADA",
                              "NO_CINE_AREA_DETALHADA", "TP_GRAU_ACADEMICO",
                              "TP_MODALIDADE_ENSINO", "TP_NIVEL_ACADEMICO",
                              "TP_SITUACAO", "IN_GRATUITO"]].set_index("CO_CURSO", drop=False)

    # ── DIM 1: curso presencial ────────────────────────────────────────────────
    pres = curso[curso["TP_MODALIDADE_ENSINO"] == "1"].copy()
    d1 = pres[["NU_ANO_CENSO"] + [c for c in IDENT[1:] if c in pres.columns]
              + ["TP_SITUACAO", "IN_GRATUITO"]].copy()
    for novo, antigo in zip(GEO_LEGADO, GEO_LO):
        d1[novo] = pres[antigo].values
    d1["TP_DIMENSAO"] = "1"
    d1["QT_CURSO"] = pres["QT_CURSO"].values
    for velho, novo in VAGAS.items():
        d1[novo] = pres[velho].values
    d1 = d1.join(n2[qts], on="CO_CURSO")

    # ── DIM 3: sede de curso a distancia / semipresencial (sem UF, so vagas) ───
    ead = curso[curso["TP_MODALIDADE_ENSINO"].isin(["2", "3"])].copy()
    d3 = ead[["NU_ANO_CENSO"] + [c for c in IDENT[1:] if c in ead.columns]
             + ["TP_SITUACAO", "IN_GRATUITO"]].copy()
    for novo in GEO_LEGADO:
        d3[novo] = pd.NA
    d3["TP_DIMENSAO"] = "3"
    d3["QT_CURSO"] = ead["QT_CURSO"].values
    for velho, novo in VAGAS.items():
        d3[novo] = ead[velho].values
    for c in qts:
        d3[c] = 0   # como no 2024: a sede nao carrega alunos, os polos sim

    # ── DIM 2 / 4: polos ───────────────────────────────────────────────────────
    pol = n3[n3["TP_MODALIDADE_ENSINO"].isin(["2", "3"])].copy()
    base = pol[["NU_ANO_CENSO", "TP_ORGANIZACAO_ACADEMICA", "TP_REDE",
                "TP_CATEGORIA_ADMINISTRATIVA", "IN_COMUNITARIA", "IN_CONFESSIONAL",
                "CO_IES", "NO_CURSO", "CO_CURSO", "NO_CINE_ROTULO", "CO_CINE_ROTULO",
                "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL", "CO_CINE_AREA_ESPECIFICA",
                "NO_CINE_AREA_ESPECIFICA", "CO_CINE_AREA_DETALHADA",
                "NO_CINE_AREA_DETALHADA", "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO",
                "TP_NIVEL_ACADEMICO"]].copy()
    base["TP_SITUACAO"] = meta["TP_SITUACAO"].reindex(pol["CO_CURSO"]).values
    base["IN_GRATUITO"] = meta["IN_GRATUITO"].reindex(pol["CO_CURSO"]).values
    for novo, antigo in zip(GEO_LEGADO, GEO_LO):
        base[novo] = pol[antigo].values
    base["TP_DIMENSAO"] = ["2" if pd.notna(u) else "4" for u in pol["SG_UF_LO"]]
    base["QT_CURSO"] = 0
    for novo in VAGAS.values():
        base[novo] = 0
    d2 = pd.concat([base.reset_index(drop=True), pol[qts].reset_index(drop=True)], axis=1)

    saida = pd.concat([d1, d3, d2], ignore_index=True)
    ordem = (["NU_ANO_CENSO"] + GEO_LEGADO + ["TP_DIMENSAO"]
             + [c for c in IDENT if c not in ("NU_ANO_CENSO",)]
             + ["TP_SITUACAO", "IN_GRATUITO", "QT_CURSO"] + list(VAGAS.values()) + qts)
    saida = saida[[c for c in dict.fromkeys(ordem) if c in saida.columns]]

    # ── Conferencia do resultado final ─────────────────────────────────────────
    for col_s, total, nome in (("QT_MAT", curso["QT_MATRICULA_TOTAL"].sum(), "matriculas"),
                               ("QT_CONC", curso["QT_CONCLUINTE_TOTAL"].sum(), "concluintes")):
        s = saida[col_s].sum()
        if s > total:
            falhas.append(f"{nome}: layout reconstruido soma {int(s)} > fonte {int(total)}")
        elif s < total:
            rel(f"[AVISO] {nome}: reconstruido {int(s)} de {int(total)} na fonte.")
    if saida["QT_VG_TOTAL"].sum() != curso["QT_VAGA_TOTAL"].sum():
        falhas.append("vagas reconstruidas != vagas da tabela de cursos")
    if int(saida["QT_CURSO"].sum()) != int(curso["QT_CURSO"].sum()):
        falhas.append("QT_CURSO reconstruido != tabela de cursos")

    ies = pd.read_csv(Path(origem) / ARQ["ies"], sep=";", encoding="utf-8-sig",
                      dtype=str, low_memory=False)
    ies = ies[ies["CO_IES"].isin(set(curso["CO_IES"]))].copy()

    if falhas:
        sys.exit("[ABORTADO] O adaptador NAO gerou arquivos: a traducao nao fecha.\n  - "
                 + "\n  - ".join(falhas))

    rel(f"[OK] {len(curso)} cursos -> {len(saida)} linhas "
        f"(dim1={len(d1)}, sede EaD/semi={len(d3)}, polos={len(d2)})")
    return saida, ies


def gravar(saida, ies, destino, ano="2025", rel=print):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    arqs = {f"MICRODADOS_CADASTRO_CURSOS_{ano}.CSV": saida,
            f"MICRODADOS_ED_SUP_IES_{ano}.CSV": ies}
    for nome, df in arqs.items():
        # O ETL le latin-1. Caractere fora dele viraria "?" calado: conta e avisa.
        fora = 0
        for c in df.select_dtypes(include=["object", "string"]).columns:
            fora += int(df[c].dropna().astype(str).map(
                lambda t: t != t.encode("latin-1", "replace").decode("latin-1")).sum())
        df.to_csv(destino / nome, sep=";", index=False, encoding="latin-1",
                  errors="replace")
        rel(f"[OK] {nome} ({len(df)} linhas)"
            + (f" — {fora} celula(s) com caractere fora do latin-1 trocado por '?'"
               if fora else ""))


def main():
    ap = argparse.ArgumentParser(description="Censo 2025 (7 tabelas) -> layout legado do ETL")
    ap.add_argument("--origem", required=True, help="diretorio 'dados' do Censo 2025")
    ap.add_argument("--saida", required=True, help="diretorio de saida (vira OBS_CENSO_DIR)")
    ap.add_argument("--rotulo", required=True,
                    help="trecho do rotulo CINE do curso (ex.: FARMACIA)")
    ap.add_argument("--ano", default="2025")
    a = ap.parse_args()
    saida, ies = montar(a.origem, a.rotulo)
    gravar(saida, ies, a.saida, a.ano)


if __name__ == "__main__":
    main()
