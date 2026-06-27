"""
basedosdados_observatorio.py
Alternativa via BigQuery (Base dos Dados) — sem baixar o ZIP do Censo.
Requer conta Google e projeto BigQuery configurado.

Uso:
    pip install basedosdados
    python basedosdados_observatorio.py --projeto meu-projeto-gcp --ano 2023
    python basedosdados_observatorio.py --projeto meu-projeto-gcp --ano 2023 \
        --saida observatorio_nacional_dados.json
"""

import argparse
import json
import sys

MUN_TOTAL_UF = {
    "AC": 22,  "AL": 102, "AM": 62,  "AP": 16,  "BA": 417, "CE": 184,
    "DF": 1,   "ES": 78,  "GO": 246, "MA": 217, "MG": 853, "MS": 79,
    "MT": 142, "PA": 144, "PB": 223, "PE": 185, "PI": 224, "PR": 399,
    "RJ": 92,  "RN": 167, "RO": 52,  "RR": 15,  "RS": 497, "SC": 295,
    "SE": 75,  "SP": 645, "TO": 139,
}

CAPITAIS = {
    "AC": "Rio Branco",    "AL": "Maceió",          "AM": "Manaus",
    "AP": "Macapá",        "BA": "Salvador",         "CE": "Fortaleza",
    "DF": "Brasília",      "ES": "Vitória",          "GO": "Goiânia",
    "MA": "São Luís",      "MG": "Belo Horizonte",   "MS": "Campo Grande",
    "MT": "Cuiabá",        "PA": "Belém",            "PB": "João Pessoa",
    "PE": "Recife",        "PI": "Teresina",         "PR": "Curitiba",
    "RJ": "Rio de Janeiro","RN": "Natal",            "RO": "Porto Velho",
    "RR": "Boa Vista",     "RS": "Porto Alegre",     "SC": "Florianópolis",
    "SE": "Aracaju",       "SP": "São Paulo",        "TO": "Palmas",
}

# SQL para Base dos Dados — tabela pública do Censo INEP
QUERY_TEMPLATE = """
SELECT
    sg_uf_curso                           AS uf,
    no_municipio_curso                    AS municipio,
    co_ies,
    SUM(CAST(qt_vg_total AS INT64))       AS vagas
FROM `basedosdados.br_inep_censo_educacao_superior.curso`
WHERE
    ano = {ano}
    AND UPPER(no_cine_rotulo) LIKE '%FARM%'
    AND in_situacao_funcionamento = 1
GROUP BY 1, 2, 3
ORDER BY 1, 2
"""


def processar_df(df_bq):
    """Converte resultado BigQuery → dict por UF (mesmo formato de ingestao_observatorio_nacional)."""
    import unicodedata

    def norm(s):
        s = unicodedata.normalize("NFD", str(s).upper())
        return "".join(c for c in s if unicodedata.category(c) != "Mn")

    resultado = {}
    for uf, grp in df_bq.groupby("uf"):
        uf = str(uf).strip().upper()
        if uf not in MUN_TOTAL_UF:
            continue

        vagas_total = int(grp["vagas"].sum())
        cap = norm(CAPITAIS.get(uf, ""))
        vagas_capital = int(grp[grp["municipio"].apply(norm) == cap]["vagas"].sum())
        mun_oferta = grp["municipio"].nunique()
        mun_total = MUN_TOTAL_UF[uf]

        vagas_por_ies = grp.groupby("co_ies")["vagas"].sum().to_dict()
        n_ies = len(vagas_por_ies)
        total = sum(vagas_por_ies.values()) or 1
        hhi = round(sum((v / total) ** 2 for v in vagas_por_ies.values()), 4)
        top_sorted = sorted(vagas_por_ies.values(), reverse=True)
        cr2 = round(sum(top_sorted[:2]) / total, 4) if len(top_sorted) >= 2 else None
        cr10 = round(sum(top_sorted[:10]) / total, 4)

        resultado[uf] = {
            "vagas_total": vagas_total,
            "vagas_capital": vagas_capital,
            "municipios_total": mun_total,
            "municipios_oferta": mun_oferta,
            "municipios_deserto": mun_total - mun_oferta,
            "n_ies": n_ies,
            "HHI": hhi,
            "CR2": cr2,
            "CR10": cr10,
        }

    return resultado


def main():
    parser = argparse.ArgumentParser(description="Alternativa BigQuery → observatorio_nacional_dados.json")
    parser.add_argument("--projeto", required=True, help="ID do projeto GCP para billing")
    parser.add_argument("--ano", type=int, default=2023, help="Ano do Censo (default: 2023)")
    parser.add_argument("--saida", default="observatorio_nacional_dados.json")
    args = parser.parse_args()

    try:
        import basedosdados as bd
    except ImportError:
        sys.exit("Instale: pip install basedosdados")

    query = QUERY_TEMPLATE.format(ano=args.ano)
    print(f"[INFO] Executando query BigQuery (projeto={args.projeto}, ano={args.ano}) ...")
    print("[INFO] Nota: a Base dos Dados cobra pelo processamento de dados do projeto GCP.")

    try:
        df = bd.read_sql(query, billing_project_id=args.projeto)
    except Exception as e:
        sys.exit(f"Erro ao executar query: {e}")

    print(f"[INFO] {len(df)} linhas retornadas.")
    resultado = processar_df(df)

    soma = sum(v["municipios_total"] for v in resultado.values())
    print(f"[CHECK] Soma municípios: {soma}")

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[OK] {args.saida} gerado com {len(resultado)} UFs.")


if __name__ == "__main__":
    main()
