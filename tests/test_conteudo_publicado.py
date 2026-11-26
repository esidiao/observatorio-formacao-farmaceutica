#!/usr/bin/env python3
"""
tests/test_conteudo_publicado.py
O que a página DIZ ao leitor, lida no HTML já construído.

POR QUE ESTE TESTE EXISTE
-------------------------
A página de série histórica foi ao ar dizendo ao leitor:

    A série ainda não foi gerada. Rode `python etl/serie.py` para extrair as
    edições anteriores do Censo e preencher esta página.

Isso é o ramo `{% else %}` do template — escrito para o mantenedor, durante a
construção, quando `data/serie.json` ainda não existia. Nenhum teste reclamou,
porque nenhum teste lia a página como o leitor a lê: os portões conferiam os
NÚMEROS (que estavam certos), os links (que apontavam para arquivos existentes)
e o contraste (que passava). O texto, que é a parte que o leitor de fato
consome, não tinha portão nenhum.

O defeito é pior do que parece. Não é só feio: a página de um observatório que
promete "não estimar nada" estava admitindo, em público, que uma seção inteira
não foi produzida — e pedindo que o LEITOR rodasse o pipeline. Quem chega pelo
buscador não tem o repositório, não tem os dados e não é o mantenedor.

A DISTINÇÃO QUE O TESTE FAZ
---------------------------
Comando publicado NÃO é defeito por si. A página de autoria publica

    pip install -r requirements.txt
    python etl/pipeline.py --ano 2024

de propósito: é a promessa de reprodutibilidade do projeto, e apagá-la seria
perder o que ela afirma. A diferença é ONDE o comando aparece. Dentro de um
bloco `<pre>`, é documentação: o leitor entende que aquilo é código para quem
quiser refazer a medida. Em prosa corrente, no meio de um parágrafo, é ordem
dada a quem está lendo — e é sempre resto de desenvolvimento.

Então a regra é: remove-se todo `<pre>`, e o que sobrar não pode conter
comando nem verbo de ordem técnica.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "site" / "dist"
DATA = REPO / "data"

# Quantidades por extenso, para flagrar prosa que conta errado.
NUMERAL = {1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
           6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"}

# Comando em prosa. Fora de <pre>, qualquer um destes é ordem ao leitor.
COMANDOS = (
    r"python\s+\w+/",
    r"pip\s+install",
    r"npm\s+(?:install|run)\b",
    r"localhost:\d+",
    r"git\s+(?:clone|pull|push)\b",
)

# Marca de rascunho no TEXTO VISÍVEL (sem marcação), sem distinguir caixa.
#
# A primeira versão desta lista trazia `\bplaceholder\b`, e acusava
# `<input placeholder="ICT, cobertura, EaD…">` na busca do glossário — que é
# atributo de interface, correto e útil. Procurar no texto visível em vez de no
# HTML cru resolve a classe inteira desses enganos, em vez de abrir exceção
# para este caso.
RASCUNHO_TEXTO = (
    r"lorem ipsum",
    r"ainda não foi gerad[oa]",
    r"preencher esta página",
    r"rodar o pipeline",
)

# Marca de rascunho na MARCAÇÃO CRUA, sensível à caixa.
#
# `TODO`, `FIXME` e `XXX` só valem em caixa alta: com `re.I` o `\bTODO\b`
# acusava "Todo indicador publicado tem verbete de glossário" e "curso em todo
# estado" — a convenção de quem escreve o marcador é justamente a caixa alta, e
# respeitá-la é o que separa o marcador da palavra portuguesa.
RASCUNHO_MARCACAO = (
    r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b",
    # Jinja que não foi renderizado: chega ao leitor como lixo literal.
    r"\{\{", r"\{%",
    # Valor de Python escapando para a tela como texto.
    r">\s*(?:None|undefined|NaN)\s*<",
)


def _paginas():
    if not DIST.exists():
        raise SystemExit(
            f"[ERRO] {DIST} ausente. Rode `python site/build.py` antes.")
    for p in sorted(DIST.rglob("*.html")):
        yield p.relative_to(DIST).as_posix(), p.read_text(encoding="utf-8")


def _sem_pre(html):
    """A página sem os blocos de código, que são documentação deliberada."""
    return re.sub(r"<pre\b.*?</pre>", " ", html, flags=re.S | re.I)


def _texto_visivel(html):
    """Só o que o leitor lê: sem script, sem style, sem atributo, sem tag."""
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def test_nenhuma_pagina_manda_o_leitor_rodar_comando():
    achados = []
    for rel, html in _paginas():
        prosa = _sem_pre(html)
        for pad in COMANDOS:
            for m in re.finditer(pad, prosa, re.I):
                trecho = re.sub(r"\s+", " ", prosa[max(0, m.start() - 60):
                                                   m.end() + 40])
                achados.append(f"{rel}: {m.group()!r} em prosa — …{trecho}…")
    assert not achados, (
        "comando fora de bloco de código é ordem dada ao leitor:\n  "
        + "\n  ".join(achados))


def test_nenhuma_pagina_tem_marca_de_rascunho():
    achados = []
    for rel, html in _paginas():
        visivel = _texto_visivel(html)
        for pad in RASCUNHO_TEXTO:
            m = re.search(pad, visivel, re.I)
            if m:
                achados.append(f"{rel}: {m.group()!r} — …"
                               f"{visivel[max(0, m.start() - 60):m.end() + 60]}…")
        for pad in RASCUNHO_MARCACAO:
            m = re.search(pad, html)
            if m:
                trecho = re.sub(r"\s+", " ", html[max(0, m.start() - 60):
                                                  m.end() + 60])
                achados.append(f"{rel}: {m.group()!r} — …{trecho}…")
    assert not achados, (
        "marca de trabalho em andamento numa página publicada:\n  "
        + "\n  ".join(achados))


def test_secao_sem_dado_diz_sem_dados_e_nao_se_desculpa():
    """
    O ramo vazio de um template tem de falar a língua do leitor.

    Quando uma seção não tem dado, a regra do projeto é dizer `sem dados` — o
    mesmo rótulo que o mapa usa, o mesmo que o glossário explica. O que não
    pode é o ramo vazio descrever o estado do REPOSITÓRIO ("ainda não foi
    gerada", "rode o pipeline"), porque isso só faz sentido para quem tem o
    repositório.

    Este teste confere os templates, não a saída: o ramo vazio pode estar
    inativo hoje — era o caso da série antes de ela ser extraída — e continuar
    errado, esperando a próxima edição em que falte dado para ir ao ar.

    A lista procura CONFISSÃO SOBRE O REPOSITÓRIO, não qualquer frase sobre
    algo que falta. `offline.html.j2` diz "esta página ainda não foi guardada
    para uso offline", e isso é correto: descreve o cache do navegador DO
    LEITOR, que é coisa dele, não estado da máquina de quem publica. Um padrão
    `ainda não foi` acusaria essa frase — e um teste que acusa a prosa certa
    acaba desligado.
    """
    confissoes = (r"não foi gerad", r"\brode\b", r"\bexecute\b",
                  r"falta rodar", r"rodar o pipeline", r"preencher esta página")
    achados = []
    for arq in sorted((REPO / "site" / "templates").glob("*.j2")):
        texto = arq.read_text(encoding="utf-8")
        for pad in confissoes:
            for m in re.finditer(pad, texto, re.I):
                linha = texto[:m.start()].count("\n") + 1
                achados.append(
                    f"{arq.name}:{linha}: {m.group()!r} — "
                    f"{texto.splitlines()[linha - 1].strip()[:90]}")
    assert not achados, (
        "template fala com o mantenedor onde devia falar com o leitor:\n  "
        + "\n  ".join(achados))


def test_a_prosa_da_serie_confere_com_o_numero_de_edicoes():
    """
    O texto da série não pode contar edições diferente do que a série tem.

    DEFEITO MEDIDO, no ar, no observatório de Psicologia: a página dizia

        "Comparação entre as edições 2021 e 2022 e 2023 e 2024 … então o
         rótulo Psicologia significa a mesma coisa NOS DOIS ANOS"

    com quatro edições na série. A prosa foi escrita quando a série tinha dois
    anos; a extração depois passou para quatro, e o texto ficou. Nenhum portão
    viu, porque os NÚMEROS da tabela estavam certos — o erro estava na frase
    que os apresenta, e frase não tinha portão.

    Dois sintomas, um de cada tipo:

      * a enumeração "2021 e 2022 e 2023 e 2024", que é o `join(' e ')` de
        duas edições aplicado a quatro;
      * "nos dois anos", que é afirmação numérica falsa.

    O segundo é o grave. O primeiro é feio; o segundo diz ao leitor que a
    comparabilidade foi verificada em dois anos quando são quatro.
    """
    pagina = DIST / "serie.html"
    if not pagina.exists():
        return  # projeto sem página de série: nada a conferir
    texto = _texto_visivel(pagina.read_text(encoding="utf-8"))

    arq = DATA / "serie.json"
    if not arq.exists():
        assert "sem dados" in texto.lower(), (
            "sem `data/serie.json`, a página de série tem de dizer `sem "
            "dados` ao leitor — e não descrever o estado do repositório")
        return

    anos = [str(a) for a in json.loads(arq.read_text(encoding="utf-8"))["anos"]]
    n = len(anos)

    ausentes = [a for a in anos if a not in texto]
    assert not ausentes, (
        f"a série tem as edições {anos} e a página não nomeia {ausentes}")

    enfileirado = re.search(r"\d{4} e \d{4} e \d{4}", texto)
    assert not enfileirado, (
        f"enumeração de edições com ' e ' repetido: {enfileirado.group()!r} — "
        "é o `join(' e ')` de duas edições aplicado a mais de duas")

    erradas = [f"{palavra} anos" for k, palavra in NUMERAL.items()
               if k != n and re.search(rf"\b{palavra}s? anos\b", texto, re.I)]
    erradas += [f"{palavra} edições" for k, palavra in NUMERAL.items()
                if k != n and re.search(rf"\b{palavra} edi[çc][õo]es\b",
                                        texto, re.I)]
    assert not erradas, (
        f"a série tem {n} edições e a prosa diz {erradas} — "
        "texto escrito para outra quantidade de edições")


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK      {nome}")
            except AssertionError as e:
                falhas += 1
                print(f"  FALHOU  {nome}: {e}")
    total = sum(1 for n, f in globals().items()
                if n.startswith("test_") and callable(f))
    print(f"\n{total - falhas}/{total} testes de conteúdo publicado passaram.")
    sys.exit(1 if falhas else 0)
