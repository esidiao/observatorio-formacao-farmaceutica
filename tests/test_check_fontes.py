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


def rodar(prov, sonda, ano_hoje=2026, sonda_modificacao=None):
    """Executa check_fontes com rede e data controladas; captura saída e outputs."""
    import io
    import contextlib
    from datetime import date as date_real

    class DataFalsa(date_real):
        @classmethod
        def today(cls):
            return date_real(ano_hoje, 7, 26)

    # Por padrão a fonte por Last-Modified não traz novidade, para que cada teste
    # exercite só o eixo que lhe interessa.
    if sonda_modificacao is None:
        def sonda_modificacao(url, **kwargs):
            return True, "206", date_real(2024, 1, 1)

    outputs = {}
    originais = (pipeline._sondar, pipeline._sondar_modificacao,
                 pipeline.date, pipeline._github_output)
    pipeline._sondar = sonda
    pipeline._sondar_modificacao = sonda_modificacao
    pipeline.date = DataFalsa
    pipeline._github_output = lambda k, v: outputs.__setitem__(k, v)
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            resultado = pipeline.check_fontes(prov)
        return resultado, buffer.getvalue(), outputs
    finally:
        (pipeline._sondar, pipeline._sondar_modificacao,
         pipeline.date, pipeline._github_output) = originais


PROV = {
    "versao_censo": "2024",
    "data_extracao_fp": "2024-12-01",
    "fontes": {"enade": {"ano": 2023}},
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


# ── Fonte verificada por Last-Modified (Farmácia Popular) ────────────────────

from datetime import date as _date  # noqa: E402


def test_last_modified_mais_novo_e_novidade():
    def sonda_mod(url, **kwargs):
        return True, "206", _date(2026, 7, 13)

    novo, saida, outputs = rodar(PROV, SondaFalsa({}), sonda_modificacao=sonda_mod)
    checar(novo is True, "arquivo mais novo que a extração deveria ser novidade")
    checar("Farmácia Popular" in outputs.get("fontes_novas_detalhe", ""),
           "o detalhe deveria nomear a Farmácia Popular")


def test_last_modified_mais_antigo_nao_e_novidade():
    def sonda_mod(url, **kwargs):
        return True, "206", _date(2024, 6, 1)

    novo, saida, outputs = rodar(PROV, SondaFalsa({}), sonda_modificacao=sonda_mod)
    checar(novo is False, "arquivo anterior à extração não é novidade")
    checar("verificacao_indeterminada" not in outputs,
           "comparação bem-sucedida não é indeterminada")


def test_sem_last_modified_e_indeterminado():
    """Sem cabeçalho não há como afirmar frescor — não pode virar 'em dia'."""
    def sonda_mod(url, **kwargs):
        return True, "206", None

    novo, saida, outputs = rodar(PROV, SondaFalsa({}), sonda_modificacao=sonda_mod)
    checar(novo is False, "ausência de Last-Modified não é novidade")
    checar(outputs.get("verificacao_indeterminada") == "true",
           "sem Last-Modified o resultado DEVE ser indeterminado")


def test_url_movida_e_indeterminado():
    """404 aqui significa 'a fonte mudou de lugar', não 'não há nada novo'."""
    def sonda_mod(url, **kwargs):
        return False, "404", None

    novo, saida, outputs = rodar(PROV, SondaFalsa({}), sonda_modificacao=sonda_mod)
    checar(outputs.get("verificacao_indeterminada") == "true",
           "URL que sumiu deve ser sinalizada, não tratada como ausência de novidade")
    checar("movida" in saida or "movido" in saida,
           "o relatório deveria sugerir que a fonte pode ter sido movida")


def test_proveniencia_sem_data_e_indeterminado():
    def sonda_mod(url, **kwargs):
        return True, "206", _date(2026, 7, 13)

    prov_sem_data = {"versao_censo": "2024", "fontes": {"enade": {"ano": 2023}}}
    novo, _, outputs = rodar(prov_sem_data, SondaFalsa({}), sonda_modificacao=sonda_mod)
    checar(outputs.get("verificacao_indeterminada") == "true",
           "sem data de referência na proveniência não dá para afirmar frescor")


def main():
    for teste in (test_nada_novo, test_censo_novo_detectado, test_enade_novo_detectado,
                  test_falha_de_rede_nao_vira_sem_novidade, test_nao_sonda_o_ano_corrente,
                  test_fontes_sem_sondagem_sao_declaradas,
                  test_last_modified_mais_novo_e_novidade,
                  test_last_modified_mais_antigo_nao_e_novidade,
                  test_sem_last_modified_e_indeterminado,
                  test_url_movida_e_indeterminado,
                  test_proveniencia_sem_data_e_indeterminado):
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
