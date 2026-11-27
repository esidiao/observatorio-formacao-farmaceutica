"""
etl/serie_uf.py
Serie historica POR UF da formacao farmaceutica (Censo INEP, 2015 em diante):
data/serie_uf.json, que alimenta a pagina "Serie historica" e a secao de evolucao
de cada UF.

Uso:
    python etl/serie_uf.py --dir <dir com MICRODADOS_CADASTRO_CURSOS_AAAA.CSV e
                                MICRODADOS_ED_SUP_IES_AAAA.CSV, um par por ano>

Antes deste arquivo o observatorio so tinha a serie NACIONAL (serie_historica.json)
e o delta entre os dois ultimos Censos (historico.json). Nao havia como ver a
trajetoria de uma UF ano a ano nem compara-la com outras.

Cada indicador usa a MESMA definicao que o ETL publica em nacional.json
(ingestao_observatorio_nacional.py + complementos.py), de modo que o ultimo ponto da
serie coincide com o numero mostrado no restante do site (conferido em
tests/test_validacao.py):

    vagas_total         vagas presenciais (linhas de curso presencial, na UF do curso)
    vagas_ead           vagas de sede EaD, atribuidas a UF da IES (sede nao tem UF)
    vagas_semipresencial vagas de sede semipresencial (categoria que so existe em 2025+)
    vagas_total_real    soma das tres
    n_cursos_presencial QT_CURSO das linhas presenciais
    matriculas_total / ingressantes_total / concluintes_total
                        soma de todas as linhas com UF (polos EaD contam na UF do polo)
    n_ies               IES distintas entre as linhas com UF
    municipios_oferta   municipios distintos entre as linhas com UF (inclui polos EaD,
                        como no indicador publicado)
    pct_ead             vagas_ead / vagas_total_real

Os arquivos de 2015 a 2024 compartilham o layout (TP_DIMENSAO 1 = curso presencial,
2 = polo EaD, 3 = sede EaD) e a modalidade so assume os codigos 1 e 2; o 3
(semipresencial) so existe em 2025 (Decreto 12.456/2025), via censo2025_adaptador.py.
A definicao de modalidade mudou em 2025: a participacao da EaD e a distribuicao por
modalidade nao sao estritamente comparaveis com os anos anteriores.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependencias: pip install pandas")

REPO = Path(__file__).resolve().parent.parent
SAIDA = REPO / "data" / "serie_uf.json"

INDICADORES = ["vagas_total", "vagas_ead", "vagas_semipresencial",
               "vagas_em_extincao", "vagas_total_real",
               "pct_ead", "n_cursos_presencial", "matriculas_total",
               "ingressantes_total", "concluintes_total", "n_ies", "municipios_oferta"]
ANO_PRIMEIRO_SEMIPRESENCIAL = 2025

# SITUACAO DO CURSO: coluna que so existe de 2025 em diante.
#
# Sem ela, a serie afirmou que a EaD em Farmacia CRESCEU em 2025 — de 286.860
# para 314.778 vagas. Medido na fonte: as 314.778 sao, integralmente, cursos
# "em extincao". Nao sobrou nenhum curso de Farmacia a distancia em atividade,
# e o mesmo vale para Fisioterapia, Nutricao, Enfermagem e Fonoaudiologia,
# enquanto Administracao manteve 419 ativos — o recorte e de curso de saude,
# pelo Decreto 12.456/2025.
#
# O numero nao estava errado de conta: era mesmo a soma das vagas de formato
# 2. Estava errado de AFIRMACAO. A linha dizia ao leitor que a oferta a
# distancia se expandiu no ano em que ela foi encerrada.
#
# Regra adotada, a mesma do observatorio de Fisioterapia: vaga de curso em
# extincao NAO entra na capacidade (e oferta que a regulacao ja encerrou) e
# NAO some (sai num campo proprio, porque esses cursos continuam cheios e, no
# ano da virada, ainda receberam ingressante).
SITUACAO_ATIVIDADE = "1"


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def anos_disponiveis(diretorio):
    achados = set()
    for p in Path(diretorio).glob("MICRODADOS_CADASTRO_CURSOS_*.CSV"):
        m = re.search(r"_(\d{4})\.CSV$", p.name, flags=re.I)
        if m and (Path(diretorio) / f"MICRODADOS_ED_SUP_IES_{m.group(1)}.CSV").exists():
            achados.add(int(m.group(1)))
    return sorted(achados)


def apurar_ano(diretorio, ano):
    d = Path(diretorio)
    cols = ["SG_UF", "NO_MUNICIPIO", "CO_IES", "NO_CINE_ROTULO", "TP_MODALIDADE_ENSINO",
            "QT_VG_TOTAL", "QT_CURSO", "QT_MAT", "QT_ING", "QT_CONC"]
    arquivo = d / f"MICRODADOS_CADASTRO_CURSOS_{ano}.CSV"
    # TP_SITUACAO so existe de 2025 em diante. Pedir a coluna num arquivo
    # antigo levanta ValueError, entao a leitura tenta COM e cai para SEM —
    # e a ausencia vira "tudo em atividade", que e exatamente o que as
    # edicoes anteriores significavam: elas nao distinguiam situacao.
    try:
        df = pd.read_csv(arquivo, sep=";", encoding="latin-1", dtype=str,
                         low_memory=False, usecols=cols + ["TP_SITUACAO"])
    except ValueError:
        df = pd.read_csv(arquivo, sep=";", encoding="latin-1", dtype=str,
                         low_memory=False, usecols=cols)
        df["TP_SITUACAO"] = SITUACAO_ATIVIDADE
    df["TP_SITUACAO"] = df["TP_SITUACAO"].fillna(SITUACAO_ATIVIDADE)
    df = df[df["NO_CINE_ROTULO"].map(lambda x: "FARMACIA" in norm(x))].copy()
    if df.empty:
        sys.exit(f"[ERRO] {ano}: nenhum curso de Farmacia. Layout mudou?")
    for c in ("QT_VG_TOTAL", "QT_CURSO", "QT_MAT", "QT_ING", "QT_CONC"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    desconhecidas = set(df["TP_MODALIDADE_ENSINO"].dropna()) - {"1", "2", "3"}
    if desconhecidas:
        sys.exit(f"[ERRO] {ano}: TP_MODALIDADE_ENSINO com codigo(s) {sorted(desconhecidas)}.")
    if "3" in set(df["TP_MODALIDADE_ENSINO"]) and ano < ANO_PRIMEIRO_SEMIPRESENCIAL:
        sys.exit(f"[ERRO] {ano}: modalidade 3 antes de 2025; o dicionario mudou? Reveja antes de seguir.")

    ies = pd.read_csv(d / f"MICRODADOS_ED_SUP_IES_{ano}.CSV", sep=";", encoding="latin-1",
                      dtype=str, low_memory=False, usecols=["CO_IES", "SG_UF_IES"])
    uf_da_ies = dict(zip(ies["CO_IES"], ies["SG_UF_IES"]))

    com_uf = df[df["SG_UF"].notna()]
    ativo = df["TP_SITUACAO"] == SITUACAO_ATIVIDADE
    pres = df[(df["TP_MODALIDADE_ENSINO"] == "1") & df["SG_UF"].notna() & ativo]
    sede = df[df["SG_UF"].isna()].copy()
    sede["UF_ATRIB"] = sede["CO_IES"].map(uf_da_ies)
    sede_ativa = sede[sede["TP_SITUACAO"] == SITUACAO_ATIVIDADE]
    sede_ead = sede_ativa[sede_ativa["TP_MODALIDADE_ENSINO"] == "2"]
    sede_semi = sede_ativa[sede_ativa["TP_MODALIDADE_ENSINO"] == "3"]

    # Em extincao: de qualquer formato, com ou sem UF propria. Atribuido a UF
    # do local quando existe, e a UF da mantenedora quando nao.
    extin = df[df["TP_SITUACAO"] != SITUACAO_ATIVIDADE].copy()
    extin["UF_ATRIB"] = [
        uf if isinstance(uf, str) and uf else uf_da_ies.get(ies)
        for uf, ies in zip(extin["SG_UF"], extin["CO_IES"])]

    perdidas = int(sede[sede["UF_ATRIB"].isna()]["QT_VG_TOTAL"].sum())
    saida = {}
    for uf in sorted(set(com_uf["SG_UF"])):
        g = com_uf[com_uf["SG_UF"] == uf]
        vp = int(pres[pres["SG_UF"] == uf]["QT_VG_TOTAL"].sum())
        ve = int(sede_ead[sede_ead["UF_ATRIB"] == uf]["QT_VG_TOTAL"].sum())
        vs = int(sede_semi[sede_semi["UF_ATRIB"] == uf]["QT_VG_TOTAL"].sum())
        vx = int(extin[extin["UF_ATRIB"] == uf]["QT_VG_TOTAL"].sum())
        total = vp + ve + vs
        saida[uf] = {
            "vagas_total": vp,
            "vagas_ead": ve,
            # Nao existe antes de 2025: ausencia de categoria e null, nao zero.
            "vagas_semipresencial": vs if ano >= ANO_PRIMEIRO_SEMIPRESENCIAL else None,
            # Idem: antes de 2025 a fonte nao distinguia situacao, entao nao e
            # zero (que afirmaria "nenhum curso em extincao"), e sim ausencia.
            "vagas_em_extincao": vx if ano >= ANO_PRIMEIRO_SEMIPRESENCIAL else None,
            "vagas_total_real": total,
            "pct_ead": round(ve / total * 100, 1) if total else None,
            "n_cursos_presencial": int(pres[pres["SG_UF"] == uf]["QT_CURSO"].sum()),
            "matriculas_total": int(g["QT_MAT"].sum()),
            "ingressantes_total": int(g["QT_ING"].sum()),
            "concluintes_total": int(g["QT_CONC"].sum()),
            "n_ies": int(g["CO_IES"].nunique()),
            "municipios_oferta": int(g["NO_MUNICIPIO"].map(norm).nunique()),
        }
    return saida, perdidas


def gerar(diretorio, rel=print):
    anos = anos_disponiveis(diretorio)
    if len(anos) < 2:
        sys.exit(f"[ERRO] Preciso de pelo menos 2 anos em {diretorio}; achei {anos}.")
    faltam = [a for a in range(anos[0], anos[-1] + 1) if a not in anos]
    if faltam:
        sys.exit(f"[ERRO] Anos faltando no intervalo {anos[0]}-{anos[-1]}: {faltam}. "
                 f"Uma serie com buraco enganaria o grafico.")
    por_ano = {}
    for ano in anos:
        por_ano[ano], perdidas = apurar_ano(diretorio, ano)
        rel(f"[{ano}] {len(por_ano[ano])} UFs"
            + (f" | AVISO: {perdidas} vagas de sede sem UF atribuivel" if perdidas else ""))

    ufs = sorted({uf for a in por_ano.values() for uf in a})
    resultado = {}
    for uf in ufs:
        resultado[uf] = {k: [por_ano[a].get(uf, {}).get(k) for a in anos] for k in INDICADORES}
    return {
        "series": anos,
        "fonte": f"INEP — Microdados do Censo da Educação Superior ({anos[0]}–{anos[-1]})",
        "notas": [
            "Cada indicador usa a mesma definição do restante do observatório; o último ponto coincide com o valor publicado.",
            "Vagas EaD e semipresenciais são atribuídas à UF da mantenedora; matrículas, ingressantes e concluintes de polos EaD contam na UF do polo.",
            "A semipresencial é categoria nova do Censo 2025 (Decreto 12.456/2025): não existe antes (null). A definição de modalidade mudou em 2025, o que limita a comparação da participação da EaD com os anos anteriores.",
            "Em 2015 e 2016 o Censo não registra Farmácia EaD.",
        ],
        "ufs": resultado,
    }


def main():
    ap = argparse.ArgumentParser(description="Gera data/serie_uf.json")
    ap.add_argument("--dir", required=True, help="diretorio com um par CURSOS/IES por ano")
    ap.add_argument("--saida", default=str(SAIDA))
    a = ap.parse_args()
    s = gerar(a.dir)
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {a.saida}: {len(s['ufs'])} UFs x {len(s['series'])} anos "
          f"({s['series'][0]}-{s['series'][-1]})")


if __name__ == "__main__":
    main()
