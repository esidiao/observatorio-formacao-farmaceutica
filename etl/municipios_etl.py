"""
etl/municipios_etl.py
Gera data/municipios/<UF>.json com dados detalhados por município.

Uso:
    # Gerar todas as UFs:
    python etl/municipios_etl.py --csv MICRODADOS_CADASTRO_CURSOS_2023.CSV

    # Só GO (para testar):
    python etl/municipios_etl.py --csv MICRODADOS_CADASTRO_CURSOS_2023.CSV --uf GO
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("Instale pandas: pip install pandas")

REPO = Path(__file__).parent.parent
DATA_DIR = REPO / "data" / "municipios"

# Modalidade de ensino (TP_MODALIDADE_ENSINO)
MODALIDADE = {1: "Presencial", 2: "Semipresencial", 3: "EaD"}

# Categoria administrativa
CATEGORIA = {
    1: "Pública Federal",
    2: "Pública Estadual",
    3: "Pública Municipal",
    4: "Privada",
    5: "Privada",
    7: "Especial",
}

# Organização acadêmica
ORGANIZACAO = {
    1: "Universidade",
    2: "Centro Universitário",
    3: "Faculdade",
    4: "Instituto Federal",
    5: "CEFET",
}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def processar_uf(df_uf: "pd.DataFrame", sigla: str) -> dict:
    resultado = {}

    for mun_nome, grp in df_uf.groupby("NO_MUNICIPIO"):
        cod_mun = str(grp["CO_MUNICIPIO"].iloc[0]).zfill(7) if "CO_MUNICIPIO" in grp.columns else None

        vagas_total = int(grp["QT_VG_TOTAL"].sum())
        matriculas  = int(grp["QT_MAT"].sum())  if "QT_MAT"  in grp.columns else None
        ingressos   = int(grp["QT_ING"].sum())   if "QT_ING"  in grp.columns else None
        concluintes = int(grp["QT_CONC"].sum())  if "QT_CONC" in grp.columns else None

        # Breakdown por modalidade
        vagas_presencial = 0
        vagas_ead = 0
        if "TP_MODALIDADE_ENSINO" in grp.columns:
            for mod, sub in grp.groupby("TP_MODALIDADE_ENSINO"):
                v = int(sub["QT_VG_TOTAL"].sum())
                if mod == 1:
                    vagas_presencial = v
                elif mod == 3:
                    vagas_ead = v

        # Lista de cursos/IES
        cursos = []
        col_ies_nome = "_NO_IES" if "_NO_IES" in grp.columns else next(
            (c for c in ["NO_IES", "SG_IES", "NO_ENTIDADE"] if c in grp.columns), None
        )
        for _, row in grp.iterrows():
            nome_ies_val = row.get(col_ies_nome) if col_ies_nome else None
            c = {
                "cod_ies": str(row.get("CO_IES", "")) if "CO_IES" in grp.columns else None,
                "nome_ies": str(nome_ies_val) if nome_ies_val and str(nome_ies_val) != "nan" else None,
                "vagas": int(row["QT_VG_TOTAL"]) if pd.notna(row["QT_VG_TOTAL"]) else 0,
                "matriculas": int(row["QT_MAT"]) if "QT_MAT" in grp.columns and pd.notna(row.get("QT_MAT")) else None,
                "modalidade": MODALIDADE.get(int(row["TP_MODALIDADE_ENSINO"]), "?") if "TP_MODALIDADE_ENSINO" in grp.columns and pd.notna(row.get("TP_MODALIDADE_ENSINO")) else None,
                "categoria": CATEGORIA.get(int(row["TP_CATEGORIA_ADMINISTRATIVA"]), "?") if "TP_CATEGORIA_ADMINISTRATIVA" in grp.columns and pd.notna(row.get("TP_CATEGORIA_ADMINISTRATIVA")) else None,
                "organizacao": ORGANIZACAO.get(int(row["TP_ORGANIZACAO_ACADEMICA"]), "?") if "TP_ORGANIZACAO_ACADEMICA" in grp.columns and pd.notna(row.get("TP_ORGANIZACAO_ACADEMICA")) else None,
            }
            cursos.append(c)

        # Ordenar cursos por vagas desc
        cursos.sort(key=lambda x: x["vagas"], reverse=True)

        resultado[norm(str(mun_nome))] = {
            "nome_original": str(mun_nome),
            "cod_municipio": cod_mun,
            "vagas_total": vagas_total,
            "vagas_presencial": vagas_presencial,
            "vagas_ead": vagas_ead,
            "matriculas": matriculas,
            "ingressos": ingressos,
            "concluintes": concluintes,
            "n_cursos": len(cursos),
            "n_ies": grp["CO_IES"].nunique() if "CO_IES" in grp.columns else None,
            "cursos": cursos,
        }

    return resultado


def carregar_nomes_ies(path_csv: Path) -> dict:
    """Lê o CSV de IES e retorna dict {CO_IES: NO_IES}."""
    ies_csv = path_csv.parent / "MICRODADOS_ED_SUP_IES_2023.CSV"
    if not ies_csv.exists():
        # Tentar pelo padrão AAAA
        candidatos = list(path_csv.parent.glob("MICRODADOS_ED_SUP_IES_*.CSV"))
        ies_csv = candidatos[0] if candidatos else None
    if not ies_csv:
        print("[AVISO] CSV de IES não encontrado — nome das IES não disponível")
        return {}
    df_ies = pd.read_csv(ies_csv, sep=";", encoding="latin-1", dtype=str, usecols=["CO_IES", "NO_IES", "SG_IES"])
    return {row["CO_IES"]: row["NO_IES"] for _, row in df_ies.iterrows()}


def main():
    parser = argparse.ArgumentParser(description="ETL municipios — dados por município por UF")
    parser.add_argument("--csv", required=True, help="Caminho do MICRODADOS_CADASTRO_CURSOS_AAAA.CSV")
    parser.add_argument("--curso", default="FARMÁCIA", help="Nome do curso (default: FARMÁCIA)")
    parser.add_argument("--uf", default=None, help="Processar só esta UF (ex: GO). Omitir = todas.")
    args = parser.parse_args()

    path_csv = Path(args.csv)
    if not path_csv.exists():
        sys.exit(f"[ERRO] Arquivo não encontrado: {path_csv}")

    print(f"[INFO] Lendo {path_csv.name} ...")
    df = pd.read_csv(path_csv, sep=";", encoding="latin-1", dtype=str, low_memory=False)
    print(f"[INFO] {len(df)} linhas, {len(df.columns)} colunas")

    # Cruzar nomes das IES
    nomes_ies = carregar_nomes_ies(path_csv)
    if nomes_ies:
        print(f"[INFO] {len(nomes_ies)} IES carregadas para enriquecimento")
        df["_NO_IES"] = df["CO_IES"].map(nomes_ies)
    else:
        df["_NO_IES"] = None

    # Converter vagas e métricas para numérico
    for col in ["QT_VG_TOTAL", "QT_MAT", "QT_ING", "QT_CONC",
                "TP_MODALIDADE_ENSINO", "TP_CATEGORIA_ADMINISTRATIVA", "TP_ORGANIZACAO_ACADEMICA"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["QT_VG_TOTAL"] = df["QT_VG_TOTAL"].fillna(0)

    # Filtrar curso
    col_curso = next((c for c in ["NO_CINE_ROTULO", "NO_CURSO"] if c in df.columns), None)
    if col_curso is None:
        sys.exit("[ERRO] Coluna de curso não encontrada")

    curso_norm = norm(args.curso)
    mask = df[col_curso].apply(lambda x: curso_norm in norm(str(x)))
    df = df[mask].copy()
    print(f"[INFO] {len(df)} registros de '{args.curso}'")

    if len(df) == 0:
        sys.exit("[ERRO] Nenhum registro. Verifique --curso.")

    # UF
    col_uf = next((c for c in ["SG_UF", "CO_UF", "SG_UF_IES"] if c in df.columns), None)
    if col_uf is None:
        sys.exit("[ERRO] Coluna de UF não encontrada")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ufs = [args.uf.upper()] if args.uf else sorted(df[col_uf].dropna().unique().tolist())

    total = 0
    for sigla in ufs:
        df_uf = df[df[col_uf].str.upper() == sigla]
        if df_uf.empty:
            print(f"  [AVISO] {sigla}: nenhum dado")
            continue

        dados = processar_uf(df_uf, sigla)
        out = DATA_DIR / f"{sigla}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print(f"  [OK] {sigla}: {len(dados)} municipios -> {out.name}")
        total += 1

    print(f"\n[OK] {total} UFs processadas em data/municipios/")


if __name__ == "__main__":
    main()
