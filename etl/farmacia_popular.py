"""
etl/farmacia_popular.py
Deriva `municipios_fp` por UF — municípios atendidos pelo Programa Farmácia
Popular — a partir da fonte oficial, de forma reproduzível.

Uso:
    python etl/farmacia_popular.py                # mostra o que mudaria
    python etl/farmacia_popular.py --aplicar      # grava no CSV e na proveniência

Antes deste script o valor era mantido à mão em etl/qualidade_uf.csv, sem
registro de qual competência gerou cada número. Isso tornava impossível auditar
o ICON: não havia como saber se 4.433 vinha de 2024 ou de 2019.

Fonte: Portal de Dados Abertos do SUS (espelho sem autenticação do conjunto
"Beneficiários do Programa Farmácia Popular do Brasil"). O portal dados.gov.br
hospeda o mesmo conjunto, mas passou a exigir chave de API registrada (401 sem
credencial) — o espelho evita essa dependência.

Definição adotada: um município conta como atendido quando o indicador municipal
da competência é maior que zero, isto é, houve beneficiário atendido ali.
Município listado com indicador zero NÃO é contado — a presença da linha significa
que o município existe na malha, não que o programa opere nele.

Competência usada: dezembro do ano do Censo, NÃO a mais recente do arquivo. O ICON
divide municípios atendidos por municípios com curso, e o denominador vem do Censo.
Usar a competência mais recente (jun/2026, quando este script foi escrito) contra um
denominador de 2024 produziria um indicador temporalmente incoerente e invalidaria o
delta da série histórica. Use --competencia só para inspecionar outro período.
"""
import argparse
import collections
import csv
import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent.parent
DATA_DIR = REPO / "data"
CSV_QUALIDADE = REPO / "etl" / "qualidade_uf.csv"
PROV_FILE = DATA_DIR / "_proveniencia.json"

URL = "https://demas-dados-abertos.s3.amazonaws.com/csv/sntpbih.csv.zip"
COL_COMPETENCIA = "co_anomes"
COL_MUNICIPIO = "co_ibge"
COL_UF = "sg_uf"
COL_INDICADOR = "vl_indicador_calculado_mun"

UFS_ESPERADAS = 27


def baixar():
    """Baixa o zip e devolve (linhas, data_de_modificacao)."""
    import email.utils
    import requests

    print(f"[FP] Baixando {URL} ...")
    r = requests.get(URL, timeout=180)
    r.raise_for_status()

    modificado = None
    cabecalho = r.headers.get("Last-Modified")
    if cabecalho:
        try:
            modificado = email.utils.parsedate_to_datetime(cabecalho).date()
        except (TypeError, ValueError):
            pass

    z = zipfile.ZipFile(io.BytesIO(r.content))
    nome = z.namelist()[0]
    with z.open(nome) as f:
        linhas = list(csv.DictReader(io.TextIOWrapper(f, encoding="latin-1")))
    print(f"[FP] {len(linhas)} linhas | arquivo modificado em {modificado}")
    return linhas, modificado


def apurar(linhas, competencia_alvo=None):
    """Conta municípios atendidos por UF na competência pedida."""
    faltando = [c for c in (COL_COMPETENCIA, COL_MUNICIPIO, COL_UF, COL_INDICADOR)
                if c not in (linhas[0] if linhas else {})]
    if faltando:
        sys.exit(f"[ERRO] Colunas ausentes na fonte: {', '.join(faltando)}. "
                 f"O layout mudou — revise este script antes de confiar no número.")

    disponiveis = sorted({x[COL_COMPETENCIA] for x in linhas})
    competencia = str(competencia_alvo) if competencia_alvo else max(disponiveis)
    if competencia not in disponiveis:
        sys.exit(f"[ERRO] Competência {competencia} não existe na fonte. "
                 f"Disponíveis: {', '.join(disponiveis)}.")
    if competencia != max(disponiveis):
        print(f"[FP] Usando competência {competencia} "
              f"(a mais recente do arquivo é {max(disponiveis)}).")
    do_periodo = [x for x in linhas if x[COL_COMPETENCIA] == competencia]

    atendidos = collections.defaultdict(set)
    listados = collections.defaultdict(set)
    for x in do_periodo:
        uf = (x[COL_UF] or "").strip()
        mun = (x[COL_MUNICIPIO] or "").strip()
        if not uf or not mun:
            continue
        listados[uf].add(mun)
        try:
            if float(x[COL_INDICADOR]) > 0:
                atendidos[uf].add(mun)
        except (TypeError, ValueError):
            continue  # sem valor não é evidência de atendimento

    total_listados = sum(len(v) for v in listados.values())
    if len(listados) != UFS_ESPERADAS:
        sys.exit(f"[ERRO] {len(listados)} UFs na fonte (esperado {UFS_ESPERADAS}). "
                 f"Extração abortada.")

    print(f"[FP] Competência {competencia}: {total_listados} municípios listados, "
          f"{sum(len(v) for v in atendidos.values())} atendidos.")
    return competencia, {uf: len(muns) for uf, muns in atendidos.items()}, total_listados


def ler_csv():
    with open(CSV_QUALIDADE, encoding="utf-8", newline="") as f:
        texto = f.read()
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    campos = list(linhas[0].keys()) if linhas else []
    return linhas, campos


def comparar(atual, novo):
    """Imprime a tabela de diferenças e devolve o total de UFs alteradas."""
    print(f"\n{'UF':<4} {'atual':>7} {'novo':>7} {'delta':>7}")
    print("-" * 28)
    mudadas = 0
    for linha in atual:
        uf = linha["UF"]
        antes = linha.get("municipios_fp") or ""
        depois = novo.get(uf)
        if depois is None:
            print(f"{uf:<4} {antes:>7} {'—':>7} {'AUSENTE':>7}")
            continue
        antes_num = int(antes) if antes.strip().isdigit() else None
        marca = ""
        if antes_num != depois:
            mudadas += 1
            marca = f"{depois - antes_num:+d}" if antes_num is not None else "novo"
        print(f"{uf:<4} {antes:>7} {depois:>7} {marca:>7}")
    return mudadas


def atualizar_nacional(novo):
    """
    Aplica municipios_fp e recalcula ICON em data/nacional.json, preservando
    todo o resto.

    Deliberadamente cirúrgico, em vez de reprocessar via `pipeline.py --censo`:
    aquele caminho roda apenas ingestão + índices e produz um JSON REDUZIDO —
    medido em 33 campos perdidos nas 27 UFs (vagas_ead, por_modalidade, IDD,
    populacao, perfil docente...), porque os scripts de enriquecimento
    (censo_perfil, modalidade_split, docentes_cpc, cpc_dimensoes...) não estão
    encadeados nele. Republicar por ali destruiria boa parte do site.
    """
    caminho = DATA_DIR / "nacional.json"
    with open(caminho, encoding="utf-8") as f:
        nacional = json.load(f)

    alterados = []
    for uf, dados in nacional["ufs"].items():
        valor = novo.get(uf)
        if valor is None or dados.get("municipios_fp") == valor:
            continue
        antes_fp = dados.get("municipios_fp")
        antes_icon = dados.get("ICON")
        dados["municipios_fp"] = valor

        oferta = dados.get("municipios_oferta")
        # Mesma regra de indices_observatorio._icon: sem denominador ou sem
        # numerador o indicador é null, nunca zero.
        dados["ICON"] = (round(valor / oferta, 1)
                         if oferta and valor is not None else None)
        if dados["ICON"] != antes_icon:
            alterados.append(f"{uf}: fp {antes_fp}->{valor}, "
                             f"ICON {antes_icon}->{dados['ICON']}")
        else:
            alterados.append(f"{uf}: fp {antes_fp}->{valor} (ICON estável)")

    nacional["metadados"]["data_extracao"] = str(date.today())

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(nacional, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] nacional.json: {len(alterados)} UFs atualizadas.")
    for linha in alterados:
        print(f"       {linha}")


def aplicar(atual, campos, novo, competencia, modificado, total_listados):
    for linha in atual:
        valor = novo.get(linha["UF"])
        if valor is not None:
            linha["municipios_fp"] = str(valor)

    with open(CSV_QUALIDADE, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        escritor.writerows(atual)
    print(f"\n[OK] {CSV_QUALIDADE.name} atualizado.")

    with open(PROV_FILE, encoding="utf-8") as f:
        prov = json.load(f)
    prov["data_extracao_fp"] = str(date.today())
    fp = prov.setdefault("fontes", {}).setdefault("farmacia_popular", {})
    fp.update({
        "nome": "Programa Farmácia Popular do Brasil — Beneficiários",
        "orgao": "Ministério da Saúde",
        "url": URL,
        "espelho": ("Portal de Dados Abertos do SUS — espelho sem autenticação; "
                    "dados.gov.br exige chave de API registrada"),
        "competencia": competencia,
        "data_publicacao": str(modificado) if modificado else None,
        "municipios_listados": total_listados,
        "municipios_atendidos": sum(novo.values()),
        "definicao": ("município conta como atendido quando o indicador municipal "
                      "da competência é maior que zero"),
    })
    with open(PROV_FILE, "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
    print(f"[OK] {PROV_FILE.name} atualizado (competência {competencia}).")

    atualizar_nacional(novo)


def main():
    parser = argparse.ArgumentParser(
        description="Deriva municipios_fp por UF da fonte oficial")
    parser.add_argument("--aplicar", action="store_true",
                        help="Grava no CSV e na proveniência (padrão: só mostra)")
    parser.add_argument("--competencia", default=None,
                        help="AAAAMM a usar. Padrão: dezembro do ano do Censo "
                             "registrado em _proveniencia.json")
    args = parser.parse_args()

    alvo = args.competencia
    if not alvo:
        with open(PROV_FILE, encoding="utf-8") as f:
            ano_censo = json.load(f).get("versao_censo")
        if not ano_censo:
            sys.exit("[ERRO] _proveniencia.json sem versao_censo — informe --competencia.")
        alvo = f"{ano_censo}12"
        print(f"[FP] Competência alvo {alvo} (dezembro do Censo {ano_censo}).")

    linhas, modificado = baixar()
    competencia, novo, total_listados = apurar(linhas, alvo)
    atual, campos = ler_csv()
    mudadas = comparar(atual, novo)

    total_antes = sum(int(l["municipios_fp"]) for l in atual
                      if (l.get("municipios_fp") or "").strip().isdigit())
    # ASCII no resumo: o console padrao do Windows (cp1252) quebra em setas/bullets.
    print(f"\nTotal: {total_antes} -> {sum(novo.values())} "
          f"({sum(novo.values()) - total_antes:+d}) | {mudadas} UFs alteradas")

    if not args.aplicar:
        print("\n[SIMULAÇÃO] Nada foi gravado. Use --aplicar para persistir.")
        return
    aplicar(atual, campos, novo, competencia, modificado, total_listados)


if __name__ == "__main__":
    main()
