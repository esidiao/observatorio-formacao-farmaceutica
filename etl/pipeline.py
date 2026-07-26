"""
etl/pipeline.py
Orquestrador do pipeline de atualização do Observatório Nacional.

Uso:
    # Verificar versões das fontes sem re-extrair:
    python etl/pipeline.py --check-only

    # Pipeline completo (verifica → extrai se mudou → valida → gera dados):
    python etl/pipeline.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_AAAA.CSV

    # Forçar re-extração mesmo sem mudança:
    python etl/pipeline.py --censo caminho/arquivo.csv --forcar
"""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA_DIR = REPO / "data"
PROV_FILE = DATA_DIR / "_proveniencia.json"


def carregar_proveniencia():
    if PROV_FILE.exists():
        with open(PROV_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_proveniencia(p):
    with open(PROV_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


URL_CENSO = "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ano}.zip"


def check_fontes(prov):
    """
    Verifica se há versão nova do Censo. O candidato (ano atual - 1) só conta
    como "nova versão" se o arquivo estiver de fato publicado no INEP (HTTP 200) —
    nunca por suposição de calendário, para não disparar alertas meses antes da
    publicação real (que costuma ocorrer em outubro).
    """
    import requests

    versao_atual = prov.get("versao_censo", "0")
    ano_candidato = date.today().year - 1  # INEP publica o Censo do ano anterior
    mudou = False

    if str(versao_atual) != str(ano_candidato):
        url = URL_CENSO.format(ano=ano_candidato)
        try:
            r = requests.head(url, timeout=20, allow_redirects=True)
            mudou = r.status_code == 200
        except requests.RequestException as e:
            print(f"[CHECK] Não foi possível verificar {url}: {e}")

    if mudou:
        print(f"[CHECK] Nova versão disponível: Censo {ano_candidato} (atual: {versao_atual})")
        # GitHub Actions: exportar output
        if "GITHUB_OUTPUT" in __import__("os").environ:
            import os
            gho = os.environ.get("GITHUB_OUTPUT", "")
            if gho:
                with open(gho, "a") as f:
                    f.write("fontes_novas=true\n")
    else:
        print(f"[CHECK] Fontes em dia (Censo {versao_atual}). "
              f"Censo {ano_candidato} ainda não publicado ou já extraído.")
    return mudou


def rodar_etl(path_csv: Path, qualidade_csv: Path):
    """Roda ingestão + cálculo de índices."""
    print(f"\n[ETL] Ingestão: {path_csv.name}")
    r1 = subprocess.run(
        [sys.executable, str(REPO / "etl" / "ingestao_observatorio_nacional.py"),
         "--csv", str(path_csv),
         "--curso", "FARMÁCIA",
         "--saida", str(DATA_DIR / "observatorio_nacional_dados.json")],
        check=True,
    )

    print("\n[ETL] Cálculo de índices...")
    r2 = subprocess.run(
        [sys.executable, str(REPO / "etl" / "indices_observatorio.py"),
         "--dados", str(DATA_DIR / "observatorio_nacional_dados.json"),
         "--qualidade", str(qualidade_csv),
         "--saida", str(DATA_DIR / "final_novo.json")],
        check=True,
    )

    # Empacotar com metadados → nacional.json
    with open(DATA_DIR / "final_novo.json", encoding="utf-8") as f:
        ufs = json.load(f)

    nacional = {
        "metadados": {
            "versao_censo": str(date.today().year - 1),
            "data_extracao": str(date.today()),
            "fontes": {
                "censo": f"INEP/Censo da Educação Superior {date.today().year - 1}",
                "enade": f"INEP/Microdados ENADE {date.today().year - 1}",
                "farmacia_popular": "Ministério da Saúde/dados.gov.br",
            },
        },
        "ufs": ufs,
    }

    with open(DATA_DIR / "nacional.json", "w", encoding="utf-8") as f:
        json.dump(nacional, f, ensure_ascii=False, indent=2)

    print(f"[OK] data/nacional.json atualizado com {len(ufs)} UFs.")
    (DATA_DIR / "final_novo.json").unlink(missing_ok=True)


def rodar_validacao():
    print("\n[VALIDAÇÃO] Rodando portão de qualidade...")
    r = subprocess.run(
        [sys.executable, str(REPO / "tests" / "test_validacao.py")],
        check=False,
    )
    if r.returncode != 0:
        sys.exit("[ABORTADO] Validação falhou. Dados NÃO publicados.")
    print("[OK] Validação passou.")


def main():
    parser = argparse.ArgumentParser(description="Pipeline ETL do Observatório Nacional")
    parser.add_argument("--check-only", action="store_true",
                        help="Apenas verifica versões das fontes, sem re-extrair")
    parser.add_argument("--censo", default=None,
                        help="Caminho para MICRODADOS_CADASTRO_CURSOS_AAAA.CSV")
    parser.add_argument("--qualidade", default=str(REPO / "etl" / "qualidade_uf.csv"),
                        help="CSV de qualidade (CC/ENADE/IDD por UF)")
    parser.add_argument("--forcar", action="store_true",
                        help="Forçar re-extração mesmo sem mudança nas fontes")
    args = parser.parse_args()

    prov = carregar_proveniencia()

    if args.check_only:
        check_fontes(prov)
        return

    mudou = args.forcar or check_fontes(prov)

    if not mudou:
        print("[INFO] Nenhuma atualização necessária.")
        return

    if not args.censo:
        sys.exit("[ERRO] Informe --censo <caminho do CSV>. "
                 "O arquivo de microdados do Censo INEP não está no repositório por ser muito grande (>300MB).")

    path_csv = Path(args.censo)
    if not path_csv.exists():
        sys.exit(f"[ERRO] Arquivo não encontrado: {path_csv}")

    rodar_etl(path_csv, Path(args.qualidade))
    rodar_validacao()

    # Atualizar proveniência
    prov["versao_censo"] = str(date.today().year - 1)
    prov["data_extracao_censo"] = str(date.today())
    salvar_proveniencia(prov)
    print(f"[OK] _proveniencia.json atualizado.")


if __name__ == "__main__":
    main()
