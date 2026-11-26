"""
tests/test_acessibilidade.py
Acessibilidade MEDIDA, não presumida.

Este é o primeiro observatório da família, e o único de outra geração: a
paleta aqui são `--navy`, `--blue` e `--gold`, não os `--deep`/`--mid`/`--warm`
dos irmãos, e não existe escala sequencial — só a divergente RdBu. Por isso o
teste é próprio, e não cópia do deles.

POR QUE ELE EXISTE
------------------
Contraste e semântica de tabela são a classe de defeito que não aparece para
quem revisa: a página continua bonita, nenhum erro vai ao console, nenhum teste
de dado falha. Só falha para quem lê com pouca visão, com daltonismo, por
leitor de tela, ou no celular sob sol.

Ao ser escrito, este teste encontrou três coisas neste repositório — todas no
ar, todas invisíveis para quem olha a tela:

  · as 2.069 tabelas do sítio, sem `<caption>`;
  · nenhuma regra `prefers-reduced-motion`, ou seja, quem pede menos movimento
    no sistema recebia o mesmo movimento;
  · nas páginas de UF, a folha do projeto carregada ANTES do `leaflet.css`,
    o que inverte a cascata e devolve os controles de zoom aos 30px do padrão
    do Leaflet — abaixo do alvo de toque que o próprio projeto define.

Roda como script ou sob pytest.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSS = REPO / "site" / "static" / "css" / "style.css"
JS = REPO / "site" / "static" / "js" / "app.js"
DIST = REPO / "site" / "dist"

MINIMO_TEXTO = 4.5
MINIMO_GRANDE = 3.0


# --------------------------------------------------------------------------- #
# Contraste
# --------------------------------------------------------------------------- #

def _rgb(cor):
    cor = cor.strip().lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def _luminancia(cor):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(cor)
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _contraste(a, b):
    la, lb = _luminancia(a), _luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _tokens():
    texto = CSS.read_text(encoding="utf-8")
    i = texto.index(":root")
    bloco = texto[i:texto.index("}", i)]
    return {nome: valor for nome, valor in
            re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{3,6})\s*;", bloco)}


def _regras(css):
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = " ".join(m.group(1).split())
        if sel and not sel.startswith("@"):
            yield sel, m.group(2)


def test_pares_de_contraste_do_texto():
    """Cada par abaixo existe de fato no CSS — não é catálogo de possibilidades."""
    t = _tokens()
    pares = [
        ("corpo sobre o papel", t["text"], t["bg"], MINIMO_TEXTO),
        ("corpo sobre a superfície", t["text"], t["surface"], MINIMO_TEXTO),
        ("texto apagado sobre o papel", t["text-muted"], t["bg"], MINIMO_TEXTO),
        ("link sobre o papel", t["blue"], t["bg"], MINIMO_TEXTO),
        ("branco sobre o azul-marinho", "#FFFFFF", t["navy"], MINIMO_TEXTO),
        ("branco sobre o azul", "#FFFFFF", t["blue"], MINIMO_TEXTO),
        # O ouro institucional mede 3,47 sobre o papel: serve para contorno e
        # marcador, que pedem 3,0, e NÃO para texto. Quem pinta texto é o tom
        # forte — a mesma divisão que o observatório de Administração faz.
        ("ouro forte sobre o papel (texto)", t["gold-forte"], t["bg"],
         MINIMO_TEXTO),
        ("ouro institucional sobre o papel (contorno de foco)",
         t["gold"], t["bg"], MINIMO_GRANDE),
        ("destaque sobre o papel", t["accent"], t["bg"], MINIMO_TEXTO),
    ]
    problemas = []
    for rotulo, frente, fundo, minimo in pares:
        valor = _contraste(frente, fundo)
        if valor < minimo:
            problemas.append(
                f"{rotulo}: {frente} sobre {fundo} = {valor:.2f} "
                f"(mínimo {minimo})")
    assert not problemas, "contraste insuficiente:\n  - " + "\n  - ".join(problemas)


def test_cores_escritas_sobre_o_fundo_escuro():
    """
    Toda cor declarada numa área de fundo institucional, conferida.

    A lista não está escrita aqui: é derivada do CSS a cada execução,
    procurando quem pinta o fundo com `var(--navy)` e descendo para os
    seletores que começam por essa classe. Lista à mão não enxerga regra nova
    — e é regra nova que entra sem ninguém medir.
    """
    t = _tokens()
    css = CSS.read_text(encoding="utf-8")
    raizes = set()
    for sel, corpo in _regras(css):
        m = re.search(r"background(?:-color|-image)?\s*:\s*([^;]+);", corpo)
        if m and "var(--navy)" in m.group(1):
            for parte in sel.split(","):
                raiz = re.match(r"\.[\w-]+", parte.strip())
                if raiz:
                    raizes.add(raiz.group())
    assert raizes, (
        "não achei nenhuma regra que pinte o fundo com var(--navy). Se a "
        "estrutura do CSS mudou, conserte este teste: sem raiz, ele não está "
        "aprovando nada, está calado.")

    problemas = []
    for sel, corpo in _regras(css):
        for parte in sel.split(","):
            parte = parte.strip()
            if not any(parte == r or parte.startswith((r + "-", r + " ", r + ":"))
                       for r in raizes):
                continue
            for m in re.finditer(r"(?<!-)color\s*:\s*(#[0-9A-Fa-f]{3,6})\s*;",
                                 corpo):
                cor = m.group(1)
                valor = _contraste(cor, t["navy"])
                if valor < MINIMO_TEXTO:
                    problemas.append(
                        f"{cor} sobre {t['navy']} = {valor:.2f} em {parte}")
    assert not problemas, "\n  - ".join(sorted(set(problemas)))


def test_escala_divergente_e_monotonica_a_partir_do_centro():
    """
    A RdBu clareia até o meio e escurece depois — nas duas metades, sem degrau.

    Numa escala divergente o ponto claro é o CENTRO, não a ponta. Uma rampa que
    não sobe monotonicamente até ele e desce depois faz o mapa mentir sobre a
    ordem dos valores, e o leitor não tem como perceber.
    """
    t = _tokens()
    passos = [_luminancia(t[f"rdbu-{i}"]) for i in range(1, 10)]
    meio = passos.index(max(passos))
    problemas = []
    if meio != 4:
        problemas.append(
            f"o passo mais claro é o rdbu-{meio + 1}, e deveria ser o do meio "
            "(rdbu-5)")
    for i in range(1, meio + 1):
        if passos[i] <= passos[i - 1]:
            problemas.append(f"rdbu-{i + 1} não é mais claro que rdbu-{i}")
    for i in range(meio + 1, 9):
        if passos[i] >= passos[i - 1]:
            problemas.append(f"rdbu-{i + 1} não é mais escuro que rdbu-{i}")
    assert not problemas, "\n  - ".join(problemas)


def test_copia_da_escala_no_js_nao_diverge_do_css():
    """
    A lista de reserva do `app.js` tem de ser a mesma escala do CSS.

    O JS lê as variáveis em tempo de execução e só usa a lista embutida quando
    a leitura falha. Essa lista é justamente a cópia que sobrevive a um `sed`
    na paleta e passa a desenhar com a cor antiga, sem erro no console: no
    observatório de Psicologia, uma cópia esquecida fez a tabela do índice e
    todo mapa desenharem com a paleta de outro projeto.
    """
    t = _tokens()
    js = JS.read_text(encoding="utf-8")
    bloco = re.search(r"escalaDoCss\(\s*'rdbu',\s*9,\s*\n?\s*\[(.*?)\]", js, re.S)
    assert bloco, (
        "não achei a lista de reserva da RdBu no app.js. Se a chamada foi "
        "renomeada, conserte o padrão aqui: um teste que não encontra o alvo "
        "não está aprovando nada, está calado.")
    reserva = [c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", bloco.group(1))]
    do_css = [t[f"rdbu-{i}"].upper() for i in range(1, 10)]
    assert reserva == do_css, (
        "a reserva do app.js divergiu do CSS:\n"
        f"  css: {do_css}\n  js : {reserva}")


def test_todo_passo_da_escala_carrega_rotulo_legivel():
    """
    Toda faixa precisa comportar número legível — por uma das duas vias.

    A RdBu é escala padrão, escolhida por segurança para daltonismo, e não se
    mexe nela. Mas dois dos nove passos são tons intermediários que não
    carregam nem branco nem escuro a 4,5: `#D6604D` mede 3,72 com branco e
    4,17 com escuro. Isso é geometria da luminância — num degradê contínuo
    sempre existe a faixa do meio —, não descuido de paleta.

    Por isso valem duas vias: ou a faixa aceita branco ou escuro direto, ou o
    projeto tem `fundoELegivel`, que clareia o fundo daquela célula até o
    texto escuro passar. Exigir só a primeira obrigaria a torcer uma escala
    padrão para fugir do meio, o que custaria a propriedade pela qual ela foi
    escolhida.
    """
    t = _tokens()
    js = JS.read_text(encoding="utf-8")
    m = re.search(r"alvo\s*=\s*alvo\s*\|\|\s*([\d.]+)\s*;", js)
    if "function fundoELegivel" in js:
        assert m and float(m.group(1)) >= MINIMO_TEXTO, (
            "fundoELegivel existe, mas o alvo não chega ao mínimo de "
            f"{MINIMO_TEXTO} — o degradê fica contínuo e o número, ilegível")
        return

    problemas = []
    for i in range(1, 10):
        cor = t[f"rdbu-{i}"]
        claro = _contraste("#FFFFFF", cor)
        escuro = _contraste(t["text"], cor)
        if max(claro, escuro) < MINIMO_TEXTO:
            problemas.append(
                f"rdbu-{i} ({cor}): branco {claro:.2f}, escuro {escuro:.2f}")
    assert not problemas, ("faixas sem rótulo legível, e sem `fundoELegivel` "
                           "para resolver:\n  - " + "\n  - ".join(problemas))


def test_cor_de_ausencia_nao_parece_o_centro_da_escala():
    """
    "Sem dados" não pode ser lido como "valor neutro".

    Numa escala divergente o risco não é a ponta, é o CENTRO: o cinza da
    ausência e o passo neutro são as duas cores dessaturadas do mapa, e
    confundi-las faz "não sei" virar "na média".
    """
    t = _tokens()
    distancia = abs(_luminancia(t["nodata"]) - _luminancia(t["rdbu-5"]))
    assert distancia > 0.15, (
        f"o cinza de ausência ({t['nodata']}) tem luminância parecida com a do "
        f"centro da escala ({t['rdbu-5']}): diferença de {distancia:.3f}")


def test_movimento_reduzido_e_respeitado():
    """
    Quem pede menos movimento no sistema tem de receber menos movimento.

    Não é preferência estética: para quem tem transtorno vestibular, enxaqueca
    com aura ou epilepsia fotossensível, movimento não pedido vai de
    desconfortável a incapacitante. O navegador já pergunta ao sistema
    operacional; cabe ao CSS responder.
    """
    css = CSS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css, (
        "o CSS não respeita `prefers-reduced-motion`")


# --------------------------------------------------------------------------- #
# O que só o HTML gerado prova
# --------------------------------------------------------------------------- #

def _paginas():
    if not DIST.exists():
        return []
    return sorted(DIST.rglob("*.html"))


def test_tabelas_tem_legenda_e_escopo():
    """
    Toda tabela precisa de `<caption>` e de `scope` nos cabeçalhos.

    Sem `caption`, quem navega por leitor de tela recebe "tabela, 12 colunas" e
    nenhuma pista do que ela contém — e navegar por tabelas é justamente como
    se lê uma página densa assim. Sem `scope`, cada célula é lida solta, sem o
    cabeçalho que lhe dá sentido: "3,41" em vez de "São Paulo, ICT, 3,41".

    A mensagem agrupa por página para não despejar milhares de linhas: o que
    interessa é qual template está sem legenda, não cada instância dele.
    """
    por_pagina = {}
    for p in _paginas():
        html = p.read_text(encoding="utf-8")
        for m in re.finditer(r"<table\b.*?</table>", html, re.S):
            tabela = m.group()
            if "<caption" not in tabela:
                por_pagina.setdefault("sem caption", set()).add(p.name)
            ths = re.findall(r"<th\b([^>]*)>", tabela)
            if ths and [a for a in ths if "scope=" not in a]:
                por_pagina.setdefault("th sem scope", set()).add(p.name)
    problemas = [f"{falha}: {len(paginas)} páginas, por exemplo "
                 f"{sorted(paginas)[:3]}"
                 for falha, paginas in sorted(por_pagina.items())]
    assert not problemas, "\n  - ".join(problemas)


def test_paginas_declaram_idioma_e_link_de_pular():
    problemas = []
    for p in _paginas():
        html = p.read_text(encoding="utf-8")
        if not re.search(r"<html[^>]*\blang=", html):
            problemas.append(f"{p.name}: <html> sem lang")
        if "pular" not in html.lower():
            problemas.append(f"{p.name}: sem link de pular para o conteúdo")
    assert not problemas, "\n  - ".join(sorted(set(problemas))[:20])


def test_imagens_tem_alternativa_textual():
    problemas = []
    for p in _paginas():
        html = p.read_text(encoding="utf-8")
        for m in re.finditer(r"<img\b([^>]*)>", html):
            if "alt=" not in m.group(1):
                problemas.append(f"{p.name}: <img> sem alt")
    assert not problemas, "\n  - ".join(sorted(set(problemas))[:20])


def test_leaflet_css_vem_antes_do_css_do_projeto():
    """
    A ordem das folhas decide quem vence por cascata.

    Com a do projeto antes, o leaflet.css vence e devolve os controles de zoom
    ao padrão de 30px — abaixo do alvo de toque que o projeto define, e logo
    nos controles que mais se usam no celular.
    """
    problemas = []
    for p in _paginas():
        html = p.read_text(encoding="utf-8")
        i_leaflet = html.find("leaflet.css")
        i_projeto = html.find("css/style.css")
        if i_leaflet >= 0 and i_projeto >= 0 and i_leaflet > i_projeto:
            problemas.append(f"{p.name}: leaflet.css depois de style.css")
    assert not problemas, (
        f"{len(problemas)} páginas com as folhas fora de ordem, por exemplo:\n  - "
        + "\n  - ".join(sorted(set(problemas))[:5]))


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
    print(f"\n{total - falhas}/{total} testes de acessibilidade passaram.")
    sys.exit(1 if falhas else 0)
