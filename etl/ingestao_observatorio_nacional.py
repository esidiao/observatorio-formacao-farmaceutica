"""
ingestao_observatorio_nacional.py
Lê microdados do Censo da Educação Superior (INEP) — arquivo de CADASTRO DE CURSOS —
e agrega por UF os indicadores estruturais do observatório:
  vagas_total, vagas_capital, municipios_total, municipios_oferta, municipios_deserto,
  n_ies, HHI, CR2, CR10.

Saída: observatorio_nacional_dados.json

Uso:
    # listar colunas disponíveis no CSV (diagnóstico):
    python ingestao_observatorio_nacional.py --csv MICRODADOS_CADASTRO_CURSOS_2023.CSV --listar-colunas

    # ingestão padrão:
    python ingestao_observatorio_nacional.py --csv MICRODADOS_CADASTRO_CURSOS_2023.CSV --curso "FARMÁCIA"

    # especificar coluna de vagas manualmente (se o script reclamar):
    python ingestao_observatorio_nacional.py --csv MICRODADOS_CADASTRO_CURSOS_2023.CSV \
        --curso "FARMÁCIA" --vagas-col QT_VG_TOTAL

Referência de capitais por UF (IBGE):
"""

import argparse
import json
import sys
import math

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale pandas: pip install pandas")

# Capitais por UF (código IBGE dos municípios)
CAPITAIS = {
    "AC": "Rio Branco",       "AL": "Maceió",          "AM": "Manaus",
    "AP": "Macapá",           "BA": "Salvador",         "CE": "Fortaleza",
    "DF": "Brasília",         "ES": "Vitória",          "GO": "Goiânia",
    "MA": "São Luís",         "MG": "Belo Horizonte",   "MS": "Campo Grande",
    "MT": "Cuiabá",           "PA": "Belém",            "PB": "João Pessoa",
    "PE": "Recife",           "PI": "Teresina",         "PR": "Curitiba",
    "RJ": "Rio de Janeiro",   "RN": "Natal",            "RO": "Porto Velho",
    "RR": "Boa Vista",        "RS": "Porto Alegre",     "SC": "Florianópolis",
    "SE": "Aracaju",          "SP": "São Paulo",        "TO": "Palmas",
}

# Número oficial de municípios por UF (IBGE 2023) — soma = 5570
MUN_TOTAL_UF = {
    "AC": 22,  "AL": 102, "AM": 62,  "AP": 16,  "BA": 417, "CE": 184,
    "DF": 1,   "ES": 78,  "GO": 246, "MA": 217, "MG": 853, "MS": 79,
    "MT": 142, "PA": 144, "PB": 223, "PE": 185, "PI": 224, "PR": 399,
    "RJ": 92,  "RN": 167, "RO": 52,  "RR": 15,  "RS": 497, "SC": 295,
    "SE": 75,  "SP": 645, "TO": 139,
}

# Nomes alternativos de capitais para normalização no CSV
CAPITAIS_NORM = {uf: nome.upper() for uf, nome in CAPITAIS.items()}


def normalizar_nome(nome):
    import unicodedata
    s = unicodedata.normalize("NFD", str(nome).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def detectar_coluna_vagas(df, candidatas=None):
    if candidatas is None:
        candidatas = [
            "QT_VG_TOTAL", "QT_VAGAS_AUTORIZADAS", "QT_VG_TOTAL_DIURNO",
            "NU_VAGAS_ANUAIS", "QT_VAGAS",
        ]
    for col in candidatas:
        if col in df.columns:
            return col
    # busca parcial
    for col in df.columns:
        if "VG" in col.upper() or "VAGA" in col.upper():
            return col
    return None


def detectar_coluna_municipio(df):
    for col in ["NO_MUNICIPIO", "NO_MUNICIPIO_CURSO", "NM_MUNICIPIO", "NO_MUN"]:
        if col in df.columns:
            return col
    for col in df.columns:
        if "MUNIC" in col.upper() and "NO" in col.upper():
            return col
    return None


def detectar_coluna_curso(df):
    # NO_CINE_ROTULO é a classificação CINE padronizada — preferida sobre o nome livre
    for col in ["NO_CINE_ROTULO", "NO_CURSO", "DS_NOME_CURSO", "NM_CURSO"]:
        if col in df.columns:
            return col
    return None


def calcular_hhi(vagas_por_ies):
    """HHI = Σ(s_i²) onde s_i = fatia de vagas da IES i."""
    total = sum(vagas_por_ies.values())
    if total == 0:
        return None
    return round(sum((v / total) ** 2 for v in vagas_por_ies.values()), 4)


def calcular_cr(vagas_por_ies, n):
    """CR_n = soma das n maiores fatias."""
    total = sum(vagas_por_ies.values())
    if total == 0 or not vagas_por_ies:
        return None
    top = sorted(vagas_por_ies.values(), reverse=True)[:n]
    return round(sum(top) / total, 4)


def main():
    parser = argparse.ArgumentParser(description="Ingestão Censo INEP → observatorio_nacional_dados.json")
    parser.add_argument("--csv", required=True, help="Caminho do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV")
    parser.add_argument("--curso", default="FARMÁCIA", help="Nome do curso a filtrar (default: FARMÁCIA)")
    parser.add_argument("--vagas-col", dest="vagas_col", default=None, help="Coluna de vagas (auto-detectada se omitida)")
    parser.add_argument("--saida", default="observatorio_nacional_dados.json")
    parser.add_argument("--listar-colunas", action="store_true", help="Lista colunas do CSV e sai")
    parser.add_argument("--uf-col", default=None, help="Coluna de UF (auto-detectada se omitida)")
    parser.add_argument("--ies-col", default=None, help="Coluna de código IES (auto-detectada se omitida)")
    args = parser.parse_args()

    print(f"[INFO] Lendo {args.csv} ...")
    df = pd.read_csv(args.csv, sep=";", encoding="latin-1", dtype=str, low_memory=False)
    print(f"[INFO] {len(df)} linhas, {len(df.columns)} colunas.")

    if args.listar_colunas:
        for c in sorted(df.columns):
            print(f"  {c}")
        sys.exit(0)

    # --- detectar colunas ---
    col_curso = detectar_coluna_curso(df)
    if col_curso is None:
        sys.exit("Não encontrei coluna de nome do curso. Use --listar-colunas para inspecionar.")

    col_uf = args.uf_col or next(
        (c for c in ["SG_UF", "CO_UF", "SG_UF_IES", "UF_CURSO"] if c in df.columns), None
    )
    if col_uf is None:
        sys.exit("Não encontrei coluna de UF. Use --uf-col.")

    col_mun = detectar_coluna_municipio(df)
    if col_mun is None:
        sys.exit("Não encontrei coluna de município. Use --listar-colunas.")

    col_vagas = args.vagas_col or detectar_coluna_vagas(df)
    if col_vagas is None:
        sys.exit("Não encontrei coluna de vagas. Use --vagas-col NOME_DA_COLUNA.")

    col_ies = args.ies_col or next(
        (c for c in ["CO_IES", "NU_IES", "CO_ENTIDADE"] if c in df.columns), None
    )

    print(f"[INFO] Usando: curso={col_curso}, UF={col_uf}, mun={col_mun}, vagas={col_vagas}, IES={col_ies}")

    # --- filtrar curso ---
    curso_norm = normalizar_nome(args.curso)
    mask = df[col_curso].apply(lambda x: normalizar_nome(str(x))).str.contains(curso_norm, na=False)
    df = df[mask].copy()
    df[col_vagas] = pd.to_numeric(df[col_vagas], errors="coerce").fillna(0).astype(int)
    print(f"[INFO] {len(df)} registros de {args.curso} encontrados.")

    if len(df) == 0:
        sys.exit("Nenhum registro encontrado. Verifique --curso e a codificação do arquivo.")

    # --- detectar coluna de capital (flag nativo do Censo INEP) ---
    col_capital = "IN_CAPITAL" if "IN_CAPITAL" in df.columns else None

    # --- agregar por UF ---
    resultado = {}
    for uf, grp in df.groupby(col_uf):
        uf = str(uf).strip().upper()
        if uf not in MUN_TOTAL_UF:
            continue  # ignora UFs inválidas

        vagas_total = int(grp[col_vagas].sum())
        muns = grp[col_mun].apply(normalizar_nome).unique().tolist()

        # usa flag IN_CAPITAL se disponível, senão match por nome
        if col_capital:
            vagas_capital = int(grp[grp[col_capital] == "1"][col_vagas].sum())
        else:
            capital_norm = normalizar_nome(CAPITAIS.get(uf, ""))
            vagas_capital = int(
                grp[grp[col_mun].apply(normalizar_nome) == capital_norm][col_vagas].sum()
            )
        mun_com_oferta = grp[col_mun].apply(normalizar_nome).nunique()
        mun_total = MUN_TOTAL_UF[uf]
        mun_deserto = mun_total - mun_com_oferta

        # concentração por IES
        vagas_por_ies = {}
        if col_ies:
            for ies, sub in grp.groupby(col_ies):
                vagas_por_ies[str(ies)] = int(sub[col_vagas].sum())
        n_ies = len(vagas_por_ies)
        hhi = calcular_hhi(vagas_por_ies) if vagas_por_ies else None
        cr2 = calcular_cr(vagas_por_ies, 2) if vagas_por_ies else None
        cr10 = calcular_cr(vagas_por_ies, 10) if vagas_por_ies else None

        resultado[uf] = {
            "vagas_total": vagas_total,
            "vagas_capital": vagas_capital,
            "municipios_total": mun_total,
            "municipios_oferta": mun_com_oferta,
            "municipios_deserto": mun_deserto,
            "municipios_com_oferta_lista": sorted(muns),
            "n_ies": n_ies,
            "HHI": hhi,
            "CR2": cr2,
            "CR10": cr10,
        }

    # --- CHECK: soma de municípios ---
    soma = sum(v["municipios_total"] for v in resultado.values())
    ufs_presentes = len(resultado)
    soma_esperada = sum(MUN_TOTAL_UF[uf] for uf in resultado)
    print(f"[CHECK] UFs encontradas: {ufs_presentes}. Soma municípios: {soma} (referência parcial: {soma_esperada})")
    if ufs_presentes == 27:
        print(f"[CHECK] Soma total 27 UFs: {soma} (esperado: 5570)")

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[OK] {args.saida} gerado com {len(resultado)} UFs.")


if __name__ == "__main__":
    main()
