"""
emec_cadastro_autorizada.py
Lê o export da Consulta Avançada do e-MEC (vagas AUTORIZADAS, farmácia, Brasil)
e opcionalmente mescla com o JSON operante (microdados Censo) → cenário duplo.

Passo semi-manual: acessar emec.mec.gov.br → Consulta Avançada → Curso "Farmácia",
abrangência Brasil → EXPORTAR → salvar o arquivo (xlsx ou csv).

Uso:
    # só converte export e-MEC → JSON autorizada:
    python emec_cadastro_autorizada.py --arq export_emec_farmacia.xlsx

    # mescla com dados operantes → dual.json:
    python emec_cadastro_autorizada.py --arq export_emec_farmacia.xlsx \
        --merge observatorio_nacional_dados.json --saida dual.json

    # listar colunas do export (diagnóstico):
    python emec_cadastro_autorizada.py --arq export_emec_farmacia.xlsx --listar-colunas
"""

import argparse
import json
import sys

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale pandas e openpyxl: pip install pandas openpyxl")

import unicodedata

MUN_TOTAL_UF = {
    "AC": 22,  "AL": 102, "AM": 62,  "AP": 16,  "BA": 417, "CE": 184,
    "DF": 1,   "ES": 78,  "GO": 246, "MA": 217, "MG": 853, "MS": 79,
    "MT": 142, "PA": 144, "PB": 223, "PE": 185, "PI": 224, "PR": 399,
    "RJ": 92,  "RN": 167, "RO": 52,  "RR": 15,  "RS": 497, "SC": 295,
    "SE": 75,  "SP": 645, "TO": 139,
}

CAPITAIS_NORM = {
    "AC": "RIO BRANCO",    "AL": "MACEIO",          "AM": "MANAUS",
    "AP": "MACAPA",        "BA": "SALVADOR",         "CE": "FORTALEZA",
    "DF": "BRASILIA",      "ES": "VITORIA",          "GO": "GOIANIA",
    "MA": "SAO LUIS",      "MG": "BELO HORIZONTE",   "MS": "CAMPO GRANDE",
    "MT": "CUIABA",        "PA": "BELEM",            "PB": "JOAO PESSOA",
    "PE": "RECIFE",        "PI": "TERESINA",         "PR": "CURITIBA",
    "RJ": "RIO DE JANEIRO","RN": "NATAL",            "RO": "PORTO VELHO",
    "RR": "BOA VISTA",     "RS": "PORTO ALEGRE",     "SC": "FLORIANOPOLIS",
    "SE": "ARACAJU",       "SP": "SAO PAULO",        "TO": "PALMAS",
}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def ler_export(path):
    if path.lower().endswith(".xlsx") or path.lower().endswith(".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str)
    return df


def detectar_col(df, candidatas):
    for c in candidatas:
        if c in df.columns:
            return c
    for c in df.columns:
        for cand in candidatas:
            if cand.split("_")[-1] in c.upper():
                return c
    return None


def agregar_emec(df):
    col_uf = detectar_col(df, ["SG_UF", "UF", "SG_UF_MANTENEDORA"])
    col_mun = detectar_col(df, ["NO_MUNICIPIO", "MUNICIPIO", "NM_MUNICIPIO"])
    col_vagas = detectar_col(df, ["QT_VAGAS_AUTORIZADAS", "QT_VG_TOTAL", "VAGAS"])

    if col_uf is None:
        sys.exit("Não encontrei coluna de UF no export e-MEC. Use --listar-colunas.")
    if col_vagas is None:
        print("[AVISO] Coluna de vagas não encontrada. Usando contagem de cursos como proxy.")

    resultado = {}
    for uf, grp in df.groupby(col_uf):
        uf = str(uf).strip().upper()
        if uf not in MUN_TOTAL_UF:
            continue

        if col_vagas:
            vagas = pd.to_numeric(grp[col_vagas], errors="coerce").fillna(0)
            vagas_total = int(vagas.sum())
            vagas_capital = 0
            if col_mun:
                cap = CAPITAIS_NORM.get(uf, "")
                mask_cap = grp[col_mun].apply(norm) == norm(cap)
                vagas_capital = int(vagas[mask_cap].sum())
        else:
            vagas_total = len(grp)
            vagas_capital = 0
            if col_mun:
                cap = CAPITAIS_NORM.get(uf, "")
                vagas_capital = int((grp[col_mun].apply(norm) == norm(cap)).sum())

        mun_oferta = grp[col_mun].apply(norm).nunique() if col_mun else None

        resultado[uf] = {
            "vagas_total_autorizada": vagas_total,
            "vagas_capital_autorizada": vagas_capital,
            "municipios_oferta_autorizada": mun_oferta,
        }
    return resultado


def mesclar(dados_operante, dados_autorizada):
    merged = {}
    todas_ufs = set(dados_operante) | set(dados_autorizada)
    for uf in todas_ufs:
        d = dict(dados_operante.get(uf, {}))
        a = dados_autorizada.get(uf, {})
        d.update(a)
        merged[uf] = d
    return merged


def main():
    parser = argparse.ArgumentParser(description="e-MEC autorizada → JSON / dual.json")
    parser.add_argument("--arq", required=True, help="Export e-MEC (.xlsx ou .csv)")
    parser.add_argument("--merge", default=None, help="JSON operante para mesclar (observatorio_nacional_dados.json)")
    parser.add_argument("--saida", default="dual.json")
    parser.add_argument("--listar-colunas", action="store_true")
    args = parser.parse_args()

    df = ler_export(args.arq)
    print(f"[INFO] {len(df)} linhas, {len(df.columns)} colunas no export e-MEC.")

    if args.listar_colunas:
        for c in sorted(df.columns):
            print(f"  {c}")
        sys.exit(0)

    dados_autorizada = agregar_emec(df)
    print(f"[INFO] Agregados {len(dados_autorizada)} UFs do e-MEC.")

    if args.merge:
        with open(args.merge, encoding="utf-8") as f:
            dados_operante = json.load(f)
        resultado = mesclar(dados_operante, dados_autorizada)
        print(f"[INFO] Mesclado com {args.merge}. Total: {len(resultado)} UFs.")
    else:
        resultado = {uf: {"municipios_total": MUN_TOTAL_UF.get(uf), **d}
                     for uf, d in dados_autorizada.items()}

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[OK] {args.saida} gerado.")


if __name__ == "__main__":
    main()
