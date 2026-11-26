#!/usr/bin/env python3
"""
tests/test_sem_vazamento.py
Nenhum observatório irmão pode aparecer neste repositório por descuido.

POR QUE ESTE TESTE EXISTE
-------------------------
Os observatórios desta família nascem uns dos outros, e cópia é exatamente o
que não se vê. Dois defeitos reais, os dois encontrados meses depois:

  * A Odontologia, nascida da Psicologia, se apresentava a INEP e DATASUS com
    o `User-Agent` `observatorio-psicologia/1.0`. O User-Agent é o canal por
    onde o operador de um servidor público reclama de tráfego indevido ou
    avisa de mudança: apontando para o projeto errado, o aviso chega a quem
    não pode agir. E a proveniência, que estes projetos publicam para que a
    origem de cada número seja verificável, afirmava origem falsa.

  * A mesma Odontologia nomeava o cache do service worker com o prefixo
    `psi-`. Como os seis sítios moram na MESMA origem do GitHub Pages, e o
    Cache Storage é por origem, o prefixo é o que separa um observatório do
    outro. Com ele errado, dois projetos disputavam o mesmo namespace.

Nos dois casos a linha veio na cópia e sobreviveu à revisão, porque parecer
idêntica ao original é o que uma cópia faz quando ninguém olha.

O QUE ELE NÃO FAZ
-----------------
Não proíbe mencionar os irmãos. Mencioná-los é correto e acontece de propósito
em vários lugares: o README aponta para a ferramenta compartilhada, a página de
autoria lista as áreas do autor, comentários explicam o que NÃO transfere de um
projeto para outro. Menção deliberada em prosa é conhecimento; nome de irmão em
identificador, caminho, URL ou rótulo de interface é resto de cópia.

A distinção é feita por ONDE o nome aparece, não por quanto.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

IRMAOS = ('fonoaudiologia', 'fonoaudiólogo', 'psicologia', 'psicólogo', 'odontologia', 'administração', 'fisioterapia', 'fisioterapeuta', 'fono', 'odonto', 'psico', 'fisio')

# Arquivos onde o nome do irmão só pode estar em prosa, nunca em código.
CODIGO = {".py", ".js", ".json", ".yml", ".yaml", ".j2", ".css", ".svg"}

PULAR_DIR = (".git/", "site/dist/", "etl/dados/", "site/static/vendor/",
             "site/static/fonts/", "site/static/geo/", "__pycache__/",
             "tests/test_sem_vazamento.py")

# O teste procura IDENTIFICADOR, não prosa.
#
# Uma primeira versão tentava classificar cada linha como prosa ou código, e
# errava nas duas direções: docstring de várias linhas tem só a primeira linha
# marcada, texto visível de página não tem marcação nenhuma, e o resultado
# acusava menções deliberadas aos irmãos — que são corretas e existem de
# propósito. Proibi-las trocaria um teste de vazamento por um teste de
# isolamento, que é outra coisa e é ruim.
#
# A distinção certa é mais simples e não precisa de heurística: prosa não tem
# `snake_case` nem CONSTANTE_EM_CAIXA_ALTA. Então o que se procura é a FORMA do
# identificador, em qualquer lugar do arquivo. "o observatório de Odontologia"
# passa; `municipios_com_odontologo` não.
#
# Este projeto se identificando como outro — o defeito real que já aconteceu —
# não tem forma de identificador e é coberto separadamente por
# `test_identidade_deste_projeto`, que confere as cadeias pelo nome.
IRMAO = r"(?:fonoaudiolog\w*|administracao|administração|fisioterap\w*|odontolog\w*|psicolog\w*|odonto|psico|fisio|fono)"
SUSPEITO = (
    re.compile(rf"\b\w+_{IRMAO}\b", re.I),
    re.compile(rf"\b{IRMAO}_\w+", re.I),
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:ADMINISTRACAO|FISIO|FISIOTERAP|FONO|ODONTO|ODONTOLOG|PSICO|PSICOLOG)[A-Z0-9_]*\b"),
)


def _arquivos():
    for p in sorted(REPO.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO).as_posix()
        if any(rel.startswith(d) or f"/{d}" in f"/{rel}" for d in PULAR_DIR):
            continue
        if p.suffix.lower() not in CODIGO and p.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            yield rel, p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def test_nenhum_irmao_em_identificador():
    """
    Nome de irmão com forma de identificador é resto de cópia.

    Se este teste falhar num caso que você julga legítimo, a correção não é
    afrouxar o padrão: é perguntar por que um identificador DESTE projeto
    carrega o nome de outro. Em prosa, mencione à vontade.
    """
    achados = []
    for rel, texto in _arquivos():
        for n, linha in enumerate(texto.splitlines(), 1):
            for pad in SUSPEITO:
                if pad.search(linha):
                    achados.append(f"{rel}:{n}: {linha.strip()[:100]}")
                    break
    assert not achados, (
        "identificador com nome de observatório irmão:\n  "
        + "\n  ".join(achados))


def test_identidade_deste_projeto():
    """
    As cadeias por onde este projeto se apresenta, conferidas por nome.

    Padrão genérico não serve aqui: `UA = "observatorio-psicologia/1.0"` é
    sintaticamente impecável e foi exatamente o defeito real de um irmão. Um
    teste que procura forma não vê isso; um que procura o nome certo, sim.

    São poucas e são fechadas, então estão listadas uma a uma. Cada entrada diz
    onde a cadeia aparece e quem a lê — porque "identidade" aqui não é marca, é
    quem o servidor público registra, o que o navegador instala e o que o cache
    do service worker separa.
    """
    casos = [
        ('site/static/manifest.json', '"short_name"',
         'Farmácia',
         'nome curto do PWA: é o rótulo que fica embaixo do ícone na tela inicial de quem instala o sítio.'),
        ('site/static/sw.js', 'const CACHE',
         'onff-',
         'prefixo do cache do service worker: os seis observatórios moram na mesma origem do GitHub Pages, e é o prefixo que delimita o que cada um pode apagar.'),
        ('.claude/launch.json', '"name"',
         'observatorio',
         'nome do servidor de desenvolvimento local.'),
    ]
    falhas = []
    for arquivo, ancora, esperado, porque in casos:
        caminho = REPO / arquivo
        if not caminho.exists():
            falhas.append(f"{arquivo}: arquivo ausente — o teste perdeu a "
                          f"âncora, conserte o teste")
            continue
        texto = caminho.read_text(encoding="utf-8")
        linhas = [l for l in texto.splitlines() if ancora in l]
        if not linhas:
            falhas.append(f"{arquivo}: não achei linha com {ancora!r} — "
                          f"o teste perdeu a âncora, conserte o teste")
            continue
        if not any(esperado in l for l in linhas):
            falhas.append(f"{arquivo}: nenhuma linha com {ancora!r} contém "
                          f"{esperado!r}. {porque}\n      achei: {linhas[:2]}")
    assert not falhas, "identidade do projeto:\n  " + "\n  ".join(falhas)


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
    print(f"\n{total - falhas}/{total} testes de vazamento passaram.")
    sys.exit(1 if falhas else 0)
