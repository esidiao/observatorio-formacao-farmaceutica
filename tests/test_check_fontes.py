"""
Testes do verificador de frescor das fontes (etl/pipeline.py).

    python tests/test_check_fontes.py

Este verificador já regrediu duas vezes, sempre no mesmo ponto: confundir
"não consegui verificar" com "não há novidade". Em 2026-07-07 ele passou a
tratar exceção de rede como ausência de novidade; a auditoria de 2026-07-26
flagrou que isso silenciava o alerta semanal por completo. Os testes abaixo
travam os três estados para que a distinção não se perca de novo.

A rede é substituída por um duplo — nada aqui depende do INEP estar de pé.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
import pipeline  # noqa: E402

falhas = []


def checar(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


class SondaFalsa:
    """Substitui pipeline._sondar. `respostas` mapeia ano → (existe, detalhe)."""

    def __init__(self, respostas, padrao=(False, "404")):
        self.respostas = respostas
        self.padrao = padrao
        self.urls = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        for ano, resposta in self.respostas.items():
            if str(ano) in url:
                return resposta
        return self.padrao


def rodar(prov, sonda, ano_hoje=2026, competencias=None):
    """Executa check_fontes com rede e data controladas; captura saída e outputs."""
    import io
    import contextlib
    from datetime import date as date_real

    class DataFalsa(date_real):
        @classmethod
        def today(cls):
            return date_real(ano_hoje, 7, 26)

    # Por padrão a Farmácia Popular não traz novidade, para que cada teste
    # exercite só o eixo que lhe interessa.
    if competencias is None:
        competencias = {"202512": 4433}

    outputs = {}
    originais = (pipeline._sondar, pipeline._competencias_disponiveis,
                 pipeline.date, pipeline._github_output)
    pipeline._sondar = sonda
    pipeline._competencias_disponiveis = lambda url, **kw: (
        sorted(competencias), competencias, "ok")
    pipeline.date = DataFalsa
    pipeline._github_output = lambda k, v: outputs.__setitem__(k, v)
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            resultado = pipeline.check_fontes(prov)
        return resultado, buffer.getvalue(), outputs
    finally:
        (pipeline._sondar, pipeline._competencias_disponiveis,
         pipeline.date, pipeline._github_output) = originais


PROV = {
    "versao_censo": "2024",
    "fontes": {
        "enade": {"ano": 2023},
        "farmacia_popular": {"competencia": "202512", "municipios_atendidos": 4433},
    },
}


def test_nada_novo():
    sonda = SondaFalsa({})  # tudo 404
    novo, saida, outputs = rodar(PROV, sonda)
    checar(novo is False, "sem novidade deveria retornar False")
    checar("fontes_novas" not in outputs, "não deveria sinalizar fontes_novas")
    checar("verificacao_indeterminada" not in outputs,
           "404 confirmado não é indeterminado")
    checar("em dia" in saida, "deveria informar que as fontes estão em dia")


def test_censo_novo_detectado():
    sonda = SondaFalsa({2025: (True, "206")})
    novo, saida, outputs = rodar(PROV, sonda)
    checar(novo is True, "Censo 2025 publicado deveria retornar True")
    checar(outputs.get("fontes_novas") == "true", "deveria sinalizar fontes_novas")
    checar("Censo 2025" in outputs.get("fontes_novas_detalhe", ""),
           "o detalhe deveria nomear a edição encontrada")


def test_enade_novo_detectado():
    # 2024 responde só na URL do ENADE; o Censo 2024 já está extraído e não é sondado.
    sonda = SondaFalsa({})
    sonda.respostas = {}

    def responder(url, **kwargs):
        sonda.urls.append(url)
        return (True, "206") if "enade_2024" in url else (False, "404")

    novo, saida, outputs = rodar(PROV, responder)
    checar(novo is True, "ENADE 2024 publicado deveria retornar True")
    checar("ENADE 2024" in outputs.get("fontes_novas_detalhe", ""),
           "o detalhe deveria nomear o ENADE 2024")


def test_falha_de_rede_nao_vira_sem_novidade():
    """O ponto que já regrediu duas vezes."""
    sonda = SondaFalsa({}, padrao=(None, "ConnectionError"))
    novo, saida, outputs = rodar(PROV, sonda)
    checar(novo is False, "indeterminado não pode ser tratado como novidade")
    checar(outputs.get("verificacao_indeterminada") == "true",
           "falha de rede DEVE sinalizar verificacao_indeterminada")
    checar("::warning::" in saida,
           "falha de rede deve emitir anotação ::warning:: visível no CI")
    checar("em dia" not in saida,
           "falha de rede JAMAIS pode ser reportada como 'fontes em dia'")


def test_nao_sonda_o_ano_corrente():
    """Censo de N sai em ~out/N+1; sondar o ano corrente é requisição garantidamente inútil."""
    sonda = SondaFalsa({})
    rodar(PROV, sonda, ano_hoje=2026)
    checar(not any("2026" in u for u in sonda.urls),
           f"não deveria sondar o ano corrente; sondou {sonda.urls}")
    checar(any("censo_da_educacao_superior_2025" in u for u in sonda.urls),
           "deveria sondar o Censo 2025")


def test_fontes_sem_sondagem_sao_declaradas():
    sonda = SondaFalsa({})
    _, saida, _ = rodar(PROV, sonda)
    for fonte in pipeline.FONTES_SEM_SONDAGEM:
        checar(fonte in saida,
               f"'{fonte}' deveria aparecer no relatório como não verificável")


# ── Farmácia Popular: verificada por competência ──────────────────────────────
#
# Esta fonte é uma série multi-competência que ganha um período por mês. Uma
# versão anterior comparava Last-Modified com a data de extração — e como o
# arquivo é tocado todo mês, isso alertava sempre, sobre um período que o site
# nem consome. Os testes abaixo travam a lógica correta: comparar COMPETÊNCIAS.

def rodar_fp(competencia_usada, total_registrado, contagens):
    """Executa só o eixo Farmácia Popular, com a fonte substituída por um duplo."""
    import io
    import contextlib

    original = pipeline._competencias_disponiveis
    pipeline._competencias_disponiveis = lambda url, **kw: (
        (sorted(contagens), contagens, "ok") if contagens else (None, None, "ConnectionError"))
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            nov, ind = pipeline._checar_farmacia_popular(
                "url-falsa", competencia_usada, total_registrado)
        return nov, ind, buffer.getvalue()
    finally:
        pipeline._competencias_disponiveis = original


def test_fp_competencia_mais_recente_em_uso():
    nov, ind, saida = rodar_fp("202512", 4433, {"202412": 4433, "202512": 4433})
    checar(not nov, f"nada mais novo que a competência em uso não é novidade: {nov}")
    checar(not ind, f"comparação bem-sucedida não é indeterminada: {ind}")
    checar("mais recente" in saida, "deveria informar que já está na mais recente")


def test_fp_competencia_nova_disponivel():
    nov, ind, saida = rodar_fp("202512", 4433,
                               {"202512": 4433, "202606": 4466})
    checar(len(nov) == 1, f"competência mais nova deveria gerar 1 novidade: {nov}")
    checar("202606" in nov[0], "a novidade deveria nomear a competência nova")
    checar("202512" in nov[0], "a novidade deveria dizer qual está em uso")


def test_fp_retificacao_retroativa():
    """Contagem do período JÁ EXTRAÍDO mudou — retificação, vale alertar."""
    nov, ind, saida = rodar_fp("202512", 4433, {"202512": 4440})
    checar(any("retificada" in x for x in nov),
           f"mudança na competência em uso deveria ser sinalizada: {nov}")
    checar("4433" in nov[0] and "4440" in nov[0],
           "o alerta deveria mostrar o antes e o depois")


def test_fp_last_modified_nao_e_usado():
    """
    Regressão: o arquivo muda todo mês. Se a lógica voltasse a olhar
    Last-Modified, este caso — mesma competência, mesma contagem — alertaria.
    """
    nov, ind, _ = rodar_fp("202512", 4433, {"202512": 4433})
    checar(not nov and not ind,
           f"série tocada sem competência nova não pode alertar: {nov} {ind}")


def test_fp_falha_de_rede_e_indeterminada():
    nov, ind, saida = rodar_fp("202512", 4433, None)
    checar(not nov, "falha de rede não é novidade")
    checar(len(ind) == 1, f"falha de rede deve ser indeterminada: {ind}")


def test_fp_sem_competencia_registrada():
    nov, ind, _ = rodar_fp(None, None, {"202512": 4433})
    checar(len(ind) == 1,
           "sem competência na proveniência não há contra o que comparar")


def test_fp_competencia_registrada_desapareceu():
    nov, ind, saida = rodar_fp("202412", 4433, {"202512": 4433, "202606": 4466})
    checar(len(ind) == 1,
           f"competência registrada ausente da fonte é indeterminado: {ind}")


def main():
    for teste in (test_nada_novo, test_censo_novo_detectado, test_enade_novo_detectado,
                  test_falha_de_rede_nao_vira_sem_novidade, test_nao_sonda_o_ano_corrente,
                  test_fontes_sem_sondagem_sao_declaradas,
                  test_fp_competencia_mais_recente_em_uso,
                  test_fp_competencia_nova_disponivel,
                  test_fp_retificacao_retroativa,
                  test_fp_last_modified_nao_e_usado,
                  test_fp_falha_de_rede_e_indeterminada,
                  test_fp_sem_competencia_registrada,
                  test_fp_competencia_registrada_desapareceu):
        antes = len(falhas)
        teste()
        print(f"  [{'OK' if len(falhas) == antes else 'FALHOU'}] {teste.__name__}")

    if falhas:
        print(f"\n[FALHOU] {len(falhas)} problema(s):\n")
        for f in falhas:
            print(f"  · {f}")
        sys.exit(1)
    print("\n[PASSOU] Verificador de fontes preserva os três estados.")


if __name__ == "__main__":
    main()
