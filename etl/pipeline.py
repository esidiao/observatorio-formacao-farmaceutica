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
# Portal de Dados Abertos do SUS, com granularidade municipal.
#
# ATENÇÃO ao verificar frescor daqui: o arquivo é uma SÉRIE multi-competência que
# recebe um período novo por mês. Logo, Last-Modified muda todo mês mesmo quando
# a competência que o site usa não mudou nada — comparar esse cabeçalho com a data
# de extração produz falso positivo garantido. O ICON usa a competência alinhada
# ao ano do Censo (dezembro daquele ano), então a pergunta certa é se ESSA
# competência existe e mudou, não se o arquivo foi tocado.
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


def _competencias_disponiveis(url, tentativas=2, espera=4):
    """
    Baixa a série e devolve (competencias, contagem_por_competencia, detalhe).

    Diferente das outras sondagens, aqui o corpo É baixado (430 KB): a informação
    de que precisamos — quais competências existem e quantos municípios cada uma
    cobre — está dentro do CSV, não em cabeçalho HTTP.

    Devolve (None, None, detalhe) quando não foi possível verificar.
    """
    import collections
    import csv as _csv
    import io
    import zipfile

    import requests

    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                ultimo = f"HTTP {r.status_code}"
            else:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                with z.open(z.namelist()[0]) as f:
                    linhas = list(_csv.DictReader(
                        io.TextIOWrapper(f, encoding="latin-1")))
                atendidos = collections.defaultdict(set)
                for x in linhas:
                    try:
                        if float(x["vl_indicador_calculado_mun"]) > 0:
                            atendidos[x["co_anomes"]].add(x["co_ibge"])
                    except (KeyError, TypeError, ValueError):
                        continue
                if not atendidos:
                    return None, None, "layout inesperado (nenhuma competência lida)"
                return (sorted(atendidos),
                        {c: len(m) for c, m in atendidos.items()},
                        "ok")
        except Exception as e:  # rede, zip corrompido, layout mudado
            ultimo = type(e).__name__
        if tentativa < tentativas - 1:
            time.sleep(espera)
    return None, None, ultimo


def _checar_farmacia_popular(url, competencia_usada, total_registrado):
    """
    Verifica a Farmácia Popular pela COMPETÊNCIA, não por Last-Modified.
    Devolve (novidades, indeterminados).

    O arquivo é uma série que ganha um período novo por mês, então Last-Modified
    muda sempre — usá-lo como sinal dispararia alerta toda semana mesmo sem
    novidade no período que o site consome. Duas perguntas úteis:

      1. existe competência mais recente que a extraída? (dado novo disponível)
      2. a competência extraída mudou de contagem? (retificação retroativa)

    A escolha de adotar ou não uma competência mais nova é editorial: o ICON
    pareia municípios atendidos (Farmácia Popular) com municípios que têm curso
    (Censo), e adiantar só o numerador amplia a defasagem entre os dois. Por isso
    o alerta informa, e a decisão fica com quem mantém.
    """
    if not competencia_usada:
        return [], ["Farmácia Popular (proveniência sem competência registrada)"]

    competencias, contagens, detalhe = _competencias_disponiveis(url)
    if competencias is None:
        print(f"[CHECK] INDETERMINADO: Farmácia Popular não pôde ser verificada ({detalhe}).")
        return [], [f"Farmácia Popular ({detalhe})"]

    usada = str(competencia_usada)
    if usada not in contagens:
        print(f"[CHECK] INDETERMINADO: a competência registrada ({usada}) não está "
              f"mais na fonte. Disponíveis: {', '.join(competencias)}.")
        return [], [f"Farmácia Popular (competência {usada} ausente na fonte)"]

    novidades = []

    atual = contagens[usada]
    if total_registrado is not None and atual != total_registrado:
        print(f"[CHECK] NOVIDADE: competência {usada} foi retificada — "
              f"{total_registrado} -> {atual} municípios atendidos.")
        novidades.append(f"Farmácia Popular {usada} retificada "
                         f"({total_registrado} -> {atual})")

    mais_novas = [c for c in competencias if c > usada]
    if mais_novas:
        recente = max(mais_novas)
        print(f"[CHECK] NOVIDADE: Farmácia Popular tem competência {recente} "
              f"({contagens[recente]} municípios); em uso: {usada} ({atual}).")
        novidades.append(f"Farmácia Popular {recente} disponível (em uso: {usada})")
    else:
        print(f"[CHECK] Farmácia Popular: {usada} é a competência mais recente "
              f"({atual} municípios atendidos).")

    return novidades, []


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

    fp = prov.get("fontes", {}).get("farmacia_popular", {}) or {}
    n, i = _checar_farmacia_popular(URL_FARMACIA_POPULAR,
                                    fp.get("competencia"),
                                    fp.get("municipios_atendidos"))
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

    empacotar(ufs)
    (DATA_DIR / "final_novo.json").unlink(missing_ok=True)


def empacotar(ufs):
    """
    Junta os indicadores por UF aos metadados e grava data/nacional.json.

    Os metadados vêm de _proveniencia.json, NUNCA do calendário. Uma versão
    anterior desta função derivava o ano do ENADE de `date.today().year - 1` e
    gravava `fontes` como strings planas — o que regredia duas correções de uma
    vez: os templates leem `meta.fontes.enade.ano` (que sumiria) e o ciclo do
    ENADE de Farmácia é trienal, então o ano do Censo não serve de proxy.
    """
    prov = carregar_proveniencia()
    fontes = prov.get("fontes")
    if not isinstance(fontes, dict) or "enade" not in fontes:
        sys.exit("[ABORTADO] _proveniencia.json sem o bloco 'fontes' esperado. "
                 "Os metadados do site vêm dele — corrija antes de publicar.")
    if not isinstance(fontes.get("enade"), dict) or "ano" not in fontes["enade"]:
        sys.exit("[ABORTADO] fontes.enade precisa ser um objeto com 'ano': os "
                 "templates leem meta.fontes.enade.ano.")

    nacional = {
        "metadados": {
            "versao_censo": str(prov.get("versao_censo", "")),
            "data_extracao": str(date.today()),
            "fontes": fontes,
        },
        "ufs": ufs,
    }

    with open(DATA_DIR / "nacional.json", "w", encoding="utf-8") as f:
        json.dump(nacional, f, ensure_ascii=False, indent=2)

    print(f"[OK] data/nacional.json atualizado com {len(ufs)} UFs "
          f"(Censo {nacional['metadados']['versao_censo']}, "
          f"ENADE {fontes['enade']['ano']}).")


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
