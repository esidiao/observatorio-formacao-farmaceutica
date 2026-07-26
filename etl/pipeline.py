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
import time
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
URL_ENADE = "https://download.inep.gov.br/microdados/microdados_enade_{ano}.zip"

# Farmácia Popular: o portal dados.gov.br passou a exigir chave de API registrada
# (401 sem credencial), mas o mesmo conjunto é espelhado sem autenticação no
# Portal de Dados Abertos do SUS. O arquivo traz co_ibge/no_municipio/sg_uf com
# competência mensal — a granularidade de que o ICON precisa — e devolve
# Last-Modified, que serve de sinal de frescor sem baixar os 430 KB inteiros.
URL_FARMACIA_POPULAR = "https://demas-dados-abertos.s3.amazonaws.com/csv/sntpbih.csv.zip"

# Fontes cuja publicação NÃO é verificável automaticamente hoje, com o motivo
# concreto. Ficam declaradas aqui para que a limitação seja visível no relatório
# semanal em vez de virar um silêncio que passa por "tudo em dia".
FONTES_SEM_SONDAGEM = {
    "e_mec": (
        "e-MEC não expõe API pública nem URL de arquivo estável; o portal é "
        "renderizado por JavaScript e não há endpoint de consulta documentado."
    ),
}


def _github_output(chave, valor):
    """Exporta um output para o GitHub Actions, se estivermos rodando nele."""
    import os
    caminho = os.environ.get("GITHUB_OUTPUT", "")
    if caminho:
        with open(caminho, "a") as f:
            f.write(f"{chave}={valor}\n")


def _sondar(url, tentativas=3, espera=4):
    """
    Sonda a existência do arquivo. Devolve (existe, detalhe):
        (True,  "200")   arquivo publicado
        (False, "404")   confirmado ausente
        (None,  "erro")  não foi possível verificar — estado INDETERMINADO

    Usa GET com Range de 1 byte em vez de HEAD: o host do INEP derruba parte das
    requisições HEAD (medido em ~1 de 3), enquanto o GET com Range respondeu 206
    de forma consistente. Sem isso, uma falha de rede era lida como "sem novidade"
    e o alerta semanal nunca dispararia quando o Censo novo saísse.
    """
    import requests

    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, timeout=30, allow_redirects=True, stream=True,
                             headers={"Range": "bytes=0-0"})
            r.close()
            if r.status_code in (200, 206):
                return True, str(r.status_code)
            if r.status_code == 404:
                return False, "404"
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            ultimo = type(e).__name__
        if tentativa < tentativas - 1:
            time.sleep(espera)
    return None, ultimo


def _sondar_modificacao(url, tentativas=3, espera=4):
    """
    Como `_sondar`, mas devolve também a data de Last-Modified:
        (existe, detalhe, data)  com `data` sendo um `date` ou None.

    Serve para fontes sem versionamento por ano no nome do arquivo, cuja única
    pista de frescor é o cabeçalho HTTP. O corpo não é baixado (Range de 1 byte).
    """
    import email.utils
    import requests

    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, timeout=30, allow_redirects=True, stream=True,
                             headers={"Range": "bytes=0-0"})
            r.close()
            if r.status_code in (200, 206):
                cabecalho = r.headers.get("Last-Modified")
                quando = None
                if cabecalho:
                    try:
                        quando = email.utils.parsedate_to_datetime(cabecalho).date()
                    except (TypeError, ValueError):
                        quando = None
                return True, str(r.status_code), quando
            if r.status_code == 404:
                return False, "404", None
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            ultimo = type(e).__name__
        if tentativa < tentativas - 1:
            time.sleep(espera)
    return None, ultimo, None


def _checar_por_modificacao(rotulo, url, data_registrada):
    """
    Verifica frescor por Last-Modified. Devolve (novidades, indeterminados).

    Sem `data_registrada` na proveniência ou sem o cabeçalho na resposta, o
    resultado é INDETERMINADO — não dá para afirmar que está em dia sem ter
    contra o que comparar.
    """
    existe, detalhe, modificado = _sondar_modificacao(url)

    if existe is None:
        print(f"[CHECK] INDETERMINADO: {rotulo} não pôde ser verificado ({detalhe}).")
        return [], [f"{rotulo} ({detalhe})"]
    if not existe:
        print(f"[CHECK] INDETERMINADO: {rotulo} não encontrado na URL conhecida "
              f"({detalhe}) — a fonte pode ter sido movida.")
        return [], [f"{rotulo} (URL respondeu {detalhe})"]
    if modificado is None:
        print(f"[CHECK] INDETERMINADO: {rotulo} respondeu {detalhe} mas sem Last-Modified.")
        return [], [f"{rotulo} (sem Last-Modified)"]
    if not data_registrada:
        print(f"[CHECK] INDETERMINADO: {rotulo} publicado em {modificado}, "
              f"mas a proveniência não registra a data da extração usada.")
        return [], [f"{rotulo} (proveniência sem data de referência)"]

    try:
        referencia = date.fromisoformat(str(data_registrada))
    except ValueError:
        print(f"[CHECK] INDETERMINADO: data de referência inválida para {rotulo} "
              f"({data_registrada!r}).")
        return [], [f"{rotulo} (data de referência inválida)"]

    if modificado > referencia:
        print(f"[CHECK] NOVIDADE: {rotulo} atualizado em {modificado} "
              f"(extração usada: {referencia}).")
        return [f"{rotulo} (atualizado em {modificado})"], []

    print(f"[CHECK] {rotulo}: sem atualização desde {referencia}.")
    return [], []


def _checar_serie_anual(rotulo, url_padrao, ano_atual, ano_limite):
    """
    Procura uma edição mais recente que `ano_atual` numa fonte cujo arquivo segue
    padrão anual de URL. Varre do ano seguinte ao registrado até `ano_limite`.

    Devolve (novidades, indeterminados) — listas de textos para o relatório.
    Um ano que não pôde ser verificado entra em `indeterminados`, nunca é
    confundido com "não existe".
    """
    novidades, indeterminados = [], []
    if not ano_atual:
        return novidades, indeterminados

    for ano in range(int(ano_atual) + 1, ano_limite + 1):
        existe, detalhe = _sondar(url_padrao.format(ano=ano))
        if existe:
            novidades.append(f"{rotulo} {ano}")
            print(f"[CHECK] NOVIDADE: {rotulo} {ano} publicado (atual: {ano_atual}).")
        elif existe is None:
            indeterminados.append(f"{rotulo} {ano} ({detalhe})")
            print(f"[CHECK] INDETERMINADO: {rotulo} {ano} não pôde ser verificado ({detalhe}).")
        else:
            print(f"[CHECK] {rotulo} {ano}: confirmadamente não publicado (404).")
    return novidades, indeterminados


def check_fontes(prov):
    """
    Verifica se há edição nova das fontes com URL previsível — Censo e ENADE.

    Uma edição só conta como publicada se o arquivo responder de fato no INEP,
    nunca por suposição de calendário: o Censo costuma sair em outubro, e alertar
    em janeiro produziria um alarme falso a cada virada de ano.

    Três estados por fonte, e "não consegui verificar" jamais vira "sem novidade":
    um erro de rede silencioso faria o alerta semanal nunca disparar.

    As fontes sem URL previsível (Farmácia Popular, e-MEC) não são sondadas e são
    listadas explicitamente ao final — a lacuna aparece no relatório em vez de
    passar por normalidade.
    """
    # Nenhuma das duas fontes publica a edição do próprio ano: o Censo de N sai
    # por volta de outubro de N+1 e o ENADE de N por volta de abril de N+2.
    # Sondar o ano corrente só geraria requisições garantidamente 404.
    ano_limite = date.today().year - 1
    novidades, indeterminados = [], []

    n, i = _checar_serie_anual("Censo", URL_CENSO,
                               prov.get("versao_censo"), ano_limite)
    novidades += n
    indeterminados += i

    ano_enade = (prov.get("fontes", {}).get("enade", {}) or {}).get("ano")
    n, i = _checar_serie_anual("ENADE", URL_ENADE, ano_enade, ano_limite)
    novidades += n
    indeterminados += i

    n, i = _checar_por_modificacao("Farmácia Popular", URL_FARMACIA_POPULAR,
                                   prov.get("data_extracao_fp"))
    novidades += n
    indeterminados += i

    if FONTES_SEM_SONDAGEM:
        print("[CHECK] Sem verificação automática (conferir manualmente):")
        for fonte, motivo in FONTES_SEM_SONDAGEM.items():
            print(f"         · {fonte}: {motivo}")

    if indeterminados:
        print(f"::warning::Verificação inconclusiva para: {'; '.join(indeterminados)}. "
              f"Pode haver edição nova sem que este alerta detecte — confira manualmente.")
        _github_output("verificacao_indeterminada", "true")

    if novidades:
        print(f"[CHECK] Novidades: {', '.join(novidades)}")
        _github_output("fontes_novas", "true")
        _github_output("fontes_novas_detalhe", ", ".join(novidades))
        return True

    if not indeterminados:
        print("[CHECK] Fontes em dia — nenhuma edição nova nas fontes sondáveis.")
    return False


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
