"""
etl/complementos.py
Produz os campos complementares de data/nacional.json que, ate 2026-07-26, nao
tinham script produtor nenhum no repositorio.

Uso:
    python etl/complementos.py              # so compara com o publicado
    python etl/complementos.py --aplicar    # grava em data/nacional.json

Contexto: 12 dos 51 campos por UF vinham de trabalho que nunca foi versionado.
Na pratica nacional.json era, em parte, artefato-FONTE: reprocessar do zero os
apagava sem forma conhecida de recuperar, e so a guarda conferir_riqueza() do
pipeline impedia a perda. Este script fecha essa lacuna.

Cada derivacao abaixo foi reconstituida por engenharia reversa e conferida contra
os valores publicados: TODAS reproduzem 27/27 UFs exatamente. O modo padrao
(sem --aplicar) refaz essa conferencia, entao uma mudanca de layout nas fontes
aparece como divergencia em vez de virar numero errado publicado.

    campo                  fonte          regra
    ---------------------  -------------  ------------------------------------
    vagas_presencial       Censo          soma de QT_VG_TOTAL nas linhas presenciais
    vagas_ead              Censo + IES    vagas de sede EaD atribuidas a UF da mantenedora
    vagas_total_real       derivado       presencial + EaD
    pct_ead                derivado       vagas_ead / vagas_total_real * 100
    n_cursos_presencial    Censo          soma de QT_CURSO nas linhas presenciais
    n_cursos_ead           Censo + IES    soma de QT_CURSO nas sedes EaD com vagas
    CPC_cont               CPC            media do CPC continuo ponderada por concluintes
    IDD                    CPC            media da nota padronizada de IDD, idem
    matriculas_total       Censo          soma de QT_MAT em todas as linhas da UF
    concluintes_total      Censo          soma de QT_CONC em todas as linhas da UF
    ead_polos_registros    Censo          linhas EaD com SG_UF preenchida
    ead_polos_municipios   Censo          municipios distintos entre essas linhas
    mun_ead_only           Censo          municipios de polo sem oferta presencial
    n_mantenedoras         Censo + IES    mantenedoras distintas na capacidade
    HHI_mantenedora        Censo + IES    HHI das vagas por mantenedora
    taxa_retencao          derivado       concluintes / matriculas * 100
    vagas_por_100k         derivado       vagas_total_real / populacao * 100000
    populacao              IBGE           agregado 6579, variavel 9324, nivel N3
    pop_ano                IBGE           ano da estimativa usada

Sobre a EaD: no Censo ela aparece em duas camadas. As linhas de SEDE (SG_UF nula)
carregam as VAGAS; as de POLO (SG_UF preenchida) carregam as MATRICULAS e tem
zero vagas. Por isso a "capacidade" de uma UF, para fins de concentracao de
mercado, e presencial-da-UF + EaD-cuja-mantenedora-e-sediada-na-UF. Somar
ingenuamente as duas camadas produz numeros sem sentido.
"""
import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale as dependencias: pip install pandas requests openpyxl")

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
NACIONAL = DATA_DIR / "nacional.json"

CENSO_DIR = Path(os.environ.get(
    "OBS_CENSO_DIR",
    "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/censo2024/"
    "microdados_censo_da_educacao_superior_2024/dados"))
CPC_XLSX = Path(os.environ.get(
    "OBS_CPC_XLSX",
    "G:/Meu Drive/Works/CLAUDE IA/observatorio_farmaceutico/CPC_2023.xlsx"))

CURSO = "FARMÁCIA"
ANO_POPULACAO_PADRAO = 2025

# Agregado 6579 = Populacao residente estimada; variavel 9324; nivel N3 = UF.
URL_IBGE = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/"
            "{ano}/variaveis/9324?localidades=N3[all]")

COD_UF = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16",
    "TO": "17", "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25",
    "PE": "26", "AL": "27", "SE": "28", "BA": "29", "MG": "31", "ES": "32",
    "RJ": "33", "SP": "35", "PR": "41", "SC": "42", "RS": "43", "MS": "50",
    "MT": "51", "GO": "52", "DF": "53",
}

CAMPOS = ["populacao", "pop_ano", "vagas_por_100k", "taxa_retencao",
          "matriculas_total", "concluintes_total", "n_mantenedoras",
          "HHI_mantenedora", "n_cursos_idd", "mun_ead_only",
          "ead_polos_municipios", "ead_polos_registros",
          "vagas_presencial", "vagas_ead", "vagas_total_real", "pct_ead",
          "n_cursos_presencial", "n_cursos_ead", "CPC_cont", "IDD"]

MOD_PRESENCIAL, MOD_EAD = "1", "2"


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def _hhi(vagas_por_grupo):
    total = sum(vagas_por_grupo.values())
    if not total:
        return None
    return round(sum((v / total) ** 2 for v in vagas_por_grupo.values()), 4)


def ler_censo():
    """Le o Censo e o cadastro de IES, ja filtrados pelo curso."""
    csv_cursos = CENSO_DIR / "MICRODADOS_CADASTRO_CURSOS_2024.CSV"
    csv_ies = CENSO_DIR / "MICRODADOS_ED_SUP_IES_2024.CSV"
    for caminho in (csv_cursos, csv_ies):
        if not caminho.exists():
            sys.exit(f"[ERRO] Nao encontrei {caminho}.\n"
                     f"       Defina OBS_CENSO_DIR com o diretorio dos microdados.")

    print(f"[CENSO] Lendo {csv_cursos.name} ...")
    df = pd.read_csv(
        csv_cursos, sep=";", encoding="latin-1", dtype=str, low_memory=False,
        usecols=["SG_UF", "NO_MUNICIPIO", "CO_IES", "NO_CINE_ROTULO",
                 "TP_MODALIDADE_ENSINO", "QT_VG_TOTAL", "QT_CURSO",
                 "QT_MAT", "QT_CONC"])

    # Mesmo filtro da ingestao principal (substring sobre o rotulo CINE
    # normalizado), para que os recortes coincidam exatamente.
    alvo = norm(CURSO)
    df = df[df["NO_CINE_ROTULO"].apply(lambda x: norm(x)).str.contains(alvo, na=False)]
    if df.empty:
        sys.exit(f"[ERRO] Nenhum registro de {CURSO} no Censo. Layout mudou?")
    for col in ("QT_VG_TOTAL", "QT_CURSO", "QT_MAT", "QT_CONC"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    ies = pd.read_csv(csv_ies, sep=";", encoding="latin-1", dtype=str,
                      low_memory=False,
                      usecols=["CO_IES", "CO_MANTENEDORA", "SG_UF_IES"])
    df["CO_MANT"] = df["CO_IES"].map(dict(zip(ies["CO_IES"], ies["CO_MANTENEDORA"])))
    uf_da_ies = dict(zip(ies["CO_IES"], ies["SG_UF_IES"]))
    print(f"[CENSO] {len(df)} registros de {CURSO}.")
    return df, uf_da_ies


def apurar_censo(df, uf_da_ies):
    """Calcula, por UF, os campos que saem do Censo."""
    presencial = df[df["TP_MODALIDADE_ENSINO"] == MOD_PRESENCIAL].copy()
    ead = df[df["TP_MODALIDADE_ENSINO"] == MOD_EAD]
    polo = ead[ead["SG_UF"].notna()]

    # Capacidade para concentracao de mercado: presencial da UF + EaD cuja
    # mantenedora e sediada nela (as linhas de sede nao tem UF propria).
    sede = ead[ead["SG_UF"].isna()].copy()
    sede["UF_ATRIB"] = sede["CO_IES"].map(uf_da_ies)
    presencial["UF_ATRIB"] = presencial["SG_UF"]
    capacidade = pd.concat([presencial, sede])

    saida = {}
    for uf in sorted(set(df["SG_UF"].dropna())):
        d_uf = df[df["SG_UF"] == uf]
        d_pres = presencial[presencial["SG_UF"] == uf]
        d_polo = polo[polo["SG_UF"] == uf]

        muns_polo = set(d_polo["NO_MUNICIPIO"].dropna())
        muns_pres = set(d_pres["NO_MUNICIPIO"].dropna())

        d_cap = capacidade[(capacidade["UF_ATRIB"] == uf) &
                           (capacidade["QT_VG_TOTAL"] > 0)]
        vagas_por_mant = {m: int(g["QT_VG_TOTAL"].sum())
                          for m, g in d_cap.groupby("CO_MANT")}

        matriculas = int(d_uf["QT_MAT"].sum())
        concluintes = int(d_uf["QT_CONC"].sum())

        d_sede = sede[sede["UF_ATRIB"] == uf]
        vagas_presencial = int(d_pres["QT_VG_TOTAL"].sum())
        vagas_ead = int(d_sede["QT_VG_TOTAL"].sum())
        vagas_total = vagas_presencial + vagas_ead

        saida[uf] = {
            "vagas_presencial": vagas_presencial,
            "vagas_ead": vagas_ead,
            "vagas_total_real": vagas_total,
            "pct_ead": (round(vagas_ead / vagas_total * 100, 1)
                        if vagas_total else None),
            "n_cursos_presencial": int(d_pres["QT_CURSO"].sum()),
            # So sedes com vaga: uma sede zerada nao representa curso ofertado.
            "n_cursos_ead": int(d_sede[d_sede["QT_VG_TOTAL"] > 0]["QT_CURSO"].sum()),
            "matriculas_total": matriculas,
            "concluintes_total": concluintes,
            # Sem matriculados nao ha taxa: null, nunca zero.
            "taxa_retencao": (round(concluintes / matriculas * 100, 1)
                              if matriculas else None),
            "ead_polos_registros": int(len(d_polo)),
            "ead_polos_municipios": len(muns_polo),
            "mun_ead_only": len(muns_polo - muns_pres),
            "n_mantenedoras": len(vagas_por_mant),
            "HHI_mantenedora": _hhi(vagas_por_mant),
        }
    return saida


def apurar_populacao(ano):
    """Estimativas populacionais por UF, direto da API do IBGE."""
    import requests

    url = URL_IBGE.format(ano=ano)
    print(f"[IBGE] Consultando estimativas de {ano} ...")
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    series = r.json()[0]["resultados"][0]["series"]
    por_codigo = {s["localidade"]["id"]: int(list(s["serie"].values())[0])
                  for s in series}

    faltando = [uf for uf, cod in COD_UF.items() if cod not in por_codigo]
    if faltando:
        sys.exit(f"[ERRO] IBGE nao retornou {len(faltando)} UFs: {faltando}")
    return {uf: por_codigo[cod] for uf, cod in COD_UF.items()}


_CPC_CACHE = {}


def _ler_cpc():
    """Le a planilha do CPC uma unica vez por execucao."""
    if "raw" not in _CPC_CACHE:
        if not CPC_XLSX.exists():
            sys.exit(f"[ERRO] Nao encontrei {CPC_XLSX}.\n"
                     f"       Defina OBS_CPC_XLSX com o caminho da planilha do CPC.")
        print(f"[CPC] Lendo {CPC_XLSX.name} ...")
        _CPC_CACHE["raw"] = pd.read_excel(CPC_XLSX, sheet_name="CPC_2023",
                                          header=0, dtype=str)
    return _CPC_CACHE["raw"]


def _media_ponderada_por_uf(coluna_alvo, casas=3):
    """
    Media de uma coluna do CPC por UF, ponderada pelos concluintes participantes.

    3 casas decimais: e a precisao com que CPC_cont e IDD foram publicados —
    arredondar para 2 nao reproduz nenhum dos dois.
    """
    raw = _ler_cpc()
    cols = {norm(c): c for c in raw.columns}

    def achar(*trechos):
        for chave, original in cols.items():
            if all(t in chave for t in trechos):
                return original
        return None

    c_area, c_uf = achar("AREA", "AVALIACAO"), achar("SIGLA", "UF")
    c_alvo, c_conc = achar(*coluna_alvo), achar("CONCLUINTES", "PARTICIPANTES")
    if not all([c_area, c_uf, c_alvo, c_conc]):
        sys.exit(f"[ERRO] Colunas para {coluna_alvo} nao localizadas no CPC. "
                 f"Layout mudou — revise antes de confiar no numero.")

    df = raw[[c_area, c_uf, c_alvo, c_conc]].copy()
    df.columns = ["area", "uf", "valor", "conc"]
    df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))]
    for col in ("valor", "conc"):
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")

    saida = {}
    for uf, grupo in df.groupby(df["uf"].apply(norm)):
        g = grupo.dropna(subset=["valor"])
        pesos = g["conc"].fillna(0)
        saida[uf] = (round(float((g["valor"] * pesos).sum() / pesos.sum()), casas)
                     if len(g) and pesos.sum() else None)
    return saida


def apurar_cpc_antigo():
    """CPC continuo medio por UF, ponderado pelos concluintes participantes."""
    raw = _ler_cpc()
    cols = {norm(c): c for c in raw.columns}

    def achar(*trechos):
        for chave, original in cols.items():
            if all(t in chave for t in trechos):
                return original
        return None

    c_area, c_uf = achar("AREA", "AVALIACAO"), achar("SIGLA", "UF")
    c_cpc, c_conc = achar("CPC", "CONTINUO"), achar("CONCLUINTES", "PARTICIPANTES")
    if not all([c_area, c_uf, c_cpc, c_conc]):
        sys.exit("[ERRO] Colunas de CPC continuo nao localizadas. Layout mudou.")

    df = raw[[c_area, c_uf, c_cpc, c_conc]].copy()
    df.columns = ["area", "uf", "cpc", "conc"]
    df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))]
    for col in ("cpc", "conc"):
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")

    saida = {}
    for uf, grupo in df.groupby(df["uf"].apply(norm)):
        g = grupo.dropna(subset=["cpc"])
        pesos = g["conc"].fillna(0)
        # 3 casas: e a precisao com que o valor foi publicado.
        saida[uf] = (round(float((g["cpc"] * pesos).sum() / pesos.sum()), 3)
                     if len(g) and pesos.sum() else None)
    return saida


def apurar_idd():
    """Cursos com IDD publicado, por UF, na planilha do CPC."""
    if not CPC_XLSX.exists():
        sys.exit(f"[ERRO] Nao encontrei {CPC_XLSX}.\n"
                 f"       Defina OBS_CPC_XLSX com o caminho da planilha do CPC.")

    raw = _ler_cpc()
    cols = {norm(c): c for c in raw.columns}

    def achar(*trechos):
        for chave, original in cols.items():
            if all(t in chave for t in trechos):
                return original
        return None

    c_area, c_uf = achar("AREA", "AVALIACAO"), achar("SIGLA", "UF")
    c_idd = achar("NOTA", "PADRONIZADA", "IDD") or achar("IDD")
    if not all([c_area, c_uf, c_idd]):
        sys.exit("[ERRO] Colunas de area/UF/IDD nao localizadas no CPC. "
                 "Layout mudou — revise antes de confiar no numero.")

    df = raw[[c_area, c_uf, c_idd]].copy()
    df.columns = ["area", "uf", "idd"]
    df = df[df["area"].apply(lambda x: "FARMACIA" in norm(x))]
    df["idd"] = pd.to_numeric(
        df["idd"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    contagem = df[df["idd"].notna()].groupby(df["uf"].apply(norm)).size()
    return {uf: int(n) for uf, n in contagem.items()}


def montar(ano_populacao):
    df, uf_da_ies = ler_censo()
    do_censo = apurar_censo(df, uf_da_ies)
    populacao = apurar_populacao(ano_populacao)
    idd = apurar_idd()
    cpc = _media_ponderada_por_uf(("CPC", "CONTINUO"))
    idd_nota = _media_ponderada_por_uf(("NOTA", "PADRONIZADA", "IDD"))

    with open(NACIONAL, encoding="utf-8") as f:
        nacional = json.load(f)

    resultado = {}
    for uf, publicado in nacional["ufs"].items():
        campos = dict(do_censo.get(uf, {}))
        campos["populacao"] = populacao.get(uf)
        # String, para casar com o tipo ja publicado (evita diff espurio no JSON).
        campos["pop_ano"] = str(ano_populacao)
        campos["n_cursos_idd"] = idd.get(uf, 0)
        campos["CPC_cont"] = cpc.get(uf)
        campos["IDD"] = idd_nota.get(uf)

        # vagas_total_real sai daqui mesmo — nao do arquivo, que dentro do
        # pipeline ainda nao tem o campo.
        vagas = campos.get("vagas_total_real")
        pop = campos["populacao"]
        campos["vagas_por_100k"] = (round(vagas / pop * 100000, 1)
                                    if vagas is not None and pop else None)
        resultado[uf] = campos
    return nacional, resultado


def _referencia_publicada():
    """
    Le nacional.json como esta no ultimo commit, nao no diretorio.

    Dentro do pipeline o arquivo em disco esta em reconstrucao — empacotar() acabou
    de reescreve-lo sem os campos daqui — entao compara-lo consigo mesmo acusaria
    297 divergencias falsas. O commit e a unica referencia estavel do publicado.
    """
    import subprocess
    try:
        saida = subprocess.run(["git", "show", "HEAD:data/nacional.json"],
                               cwd=str(REPO), check=True, capture_output=True)
        return json.loads(saida.stdout.decode("utf-8"))
    except Exception as e:
        print(f"[AVISO] Sem referencia do git ({type(e).__name__}); "
              f"conferencia contra o publicado pulada.")
        return None


def comparar(calculado):
    """Confere campo a campo contra o ultimo commit. Devolve as divergencias."""
    referencia = _referencia_publicada()
    if referencia is None:
        return []
    divergencias = []
    for uf, campos in calculado.items():
        publicado = referencia["ufs"].get(uf, {})
        for campo in CAMPOS:
            antes, depois = publicado.get(campo), campos.get(campo)
            if antes != depois:
                divergencias.append((uf, campo, antes, depois))

    total = len(calculado) * len(CAMPOS)
    print(f"\n[CONFERENCIA] {total - len(divergencias)}/{total} valores "
          f"reproduzem o publicado ({len(calculado)} UFs x {len(CAMPOS)} campos).")
    if divergencias:
        por_campo = {}
        for _, campo, _, _ in divergencias:
            por_campo[campo] = por_campo.get(campo, 0) + 1
        print("  divergencias por campo:")
        for campo, n in sorted(por_campo.items(), key=lambda x: -x[1]):
            print(f"    {campo}: {n} UFs")
        print("  primeiras:")
        for uf, campo, antes, depois in divergencias[:8]:
            print(f"    {uf}.{campo}: publicado={antes!r} calculado={depois!r}")
    return divergencias


def aplicar(nacional, calculado):
    for uf, campos in calculado.items():
        nacional["ufs"].setdefault(uf, {}).update(campos)
    with open(NACIONAL, "w", encoding="utf-8") as f:
        json.dump(nacional, f, ensure_ascii=False, indent=2)
    print(f"[OK] nacional.json atualizado: {len(CAMPOS)} campos em "
          f"{len(calculado)} UFs.")


def main():
    parser = argparse.ArgumentParser(
        description="Produz os campos complementares de nacional.json")
    parser.add_argument("--aplicar", action="store_true",
                        help="Grava em nacional.json (padrao: so confere)")
    parser.add_argument("--ano-populacao", type=int, default=ANO_POPULACAO_PADRAO,
                        help=f"Ano da estimativa do IBGE (padrao: {ANO_POPULACAO_PADRAO})")
    parser.add_argument("--permitir-divergencia", action="store_true",
                        help="Grava mesmo havendo divergencia com o publicado")
    args = parser.parse_args()

    nacional, calculado = montar(args.ano_populacao)
    divergencias = comparar(calculado)

    if not args.aplicar:
        print("\n[SIMULACAO] Nada foi gravado. Use --aplicar para persistir.")
        return

    # Divergencia aqui quase sempre significa layout de fonte alterado, nao dado
    # novo — publicar por cima apagaria valores corretos por outros errados.
    if divergencias and not args.permitir_divergencia:
        sys.exit(f"[ABORTADO] {len(divergencias)} divergencias com o publicado. "
                 f"Investigue a fonte antes de gravar, ou use "
                 f"--permitir-divergencia se a mudanca for esperada.")
    aplicar(nacional, calculado)


if __name__ == "__main__":
    main()
