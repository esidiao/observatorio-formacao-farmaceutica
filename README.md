# Observatório Nacional da Formação Farmacêutica

Site estático data-driven com indicadores de acesso territorial, qualidade e cobertura assistencial da formação farmacêutica nos 27 estados brasileiros.

## Estrutura

```
/etl            Scripts ETL (Python): ingestão, cálculo de índices, pipeline
/data           Dados versionados: nacional.json, _proveniencia.json
/site           Gerador estático (Python/Jinja2) + templates + assets
/site/dist      Site gerado — NÃO versionar (gerado pelo build)
/tests          Portão de qualidade (GO) + integridade
/.github/workflows/ci.yml   CI: valida → constrói → publica
```

## Rodar localmente

### Pré-requisitos

```bash
pip install jinja2 pandas
```

### Gerar o site

```bash
python site/build.py
```

O site é gerado em `site/dist/`. Abra `site/dist/index.html` no browser.

### Portão de qualidade (GO)

```bash
python etl/indices_observatorio.py --autoteste
# Deve imprimir [PASSOU] com ICT 0.840 / IAF 29.0 / ICON 11.3
```

### Todos os testes

```bash
python tests/test_validacao.py      # integridade dos dados publicados
python tests/test_check_fontes.py   # verificador de frescor (rede mockada)
# ou: python -m pytest tests/ -v
```

## Atualizar dados (quando o INEP publica novo Censo)

```bash
# 1. Baixar microdados do Censo em https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados
# 2. Rodar o pipeline:
python etl/pipeline.py --censo caminho/MICRODADOS_CADASTRO_CURSOS_AAAA.CSV

# O pipeline:
# - Verifica se há nova versão (--check-only para só verificar)
# - Roda ingestão → cálculo de índices → validação
# - Só atualiza data/nacional.json se a validação passar
# - Atualiza _proveniencia.json com data da extração
```

## Como o cron funciona

O arquivo `.github/workflows/ci.yml` define:

- **Push/PR**: sempre roda portão GO + testes + build
- **Segunda às 06h UTC** (`schedule`): roda `pipeline.py --check-only` e abre issue se detecta edição nova
- **`workflow_dispatch`**: permite disparar manualmente com opção de forçar re-extração

## Verificação de frescor das fontes

`pipeline.py --check-only` sonda as fontes cujo arquivo segue padrão anual de URL e
distingue **três estados** por edição:

| Estado | Significado | Efeito |
|--------|-------------|--------|
| 200 / 206 | edição publicada | abre issue de re-extração |
| 404 | confirmadamente não publicada | segue em silêncio |
| erro de rede | **indeterminado** | emite `::warning::` no resumo da execução |

A distinção é o ponto sensível: tratar falha de rede como "sem novidade" silencia o
alerta por completo, e foi o que aconteceu em duas versões anteriores.
`tests/test_check_fontes.py` trava esse comportamento.

A sondagem usa `GET` com `Range: bytes=0-0`, não `HEAD` — o host do INEP derruba
cerca de 1 em 3 requisições `HEAD`, enquanto o `GET` com faixa respondeu de forma
consistente.

| Fonte | Verificação | Observação |
|-------|-------------|------------|
| Censo da Educação Superior | ✅ automática | `microdados_censo_da_educacao_superior_{ano}.zip` |
| ENADE (microdados) | ✅ automática | `microdados_enade_{ano}.zip` |
| Farmácia Popular | ❌ manual | dados.gov.br passou a exigir chave de API registrada (401 sem credencial) |
| e-MEC | ❌ manual | sem API pública nem URL de arquivo estável; portal renderizado por JavaScript |

As duas últimas são declaradas em `FONTES_SEM_SONDAGEM` e **impressas a cada execução**,
para que a lacuna apareça no relatório em vez de passar por normalidade. Automatizar a
Farmácia Popular exigiria registrar uma chave em dados.gov.br e guardá-la como secret do
repositório — decisão pendente.

## Princípio inegociável

Nenhum dado é estimado ou inventado. Indicador sem fonte para uma UF → `null`, exibido como "sem dados" (cinza `#C9CDD2`). Todo número carrega proveniência (fonte + data de extração). O portão GO testa as fórmulas contra valores canônicos sintéticos antes de qualquer publicação.

## Indicadores

| Índice | Fórmula | Direção |
|--------|---------|---------|
| ICT | ½·(vagas_capital/vagas_total) + ½·(1 − mun_oferta/mun_total) | ↓ melhor |
| IAF | 100·média(Q, V, E) — Q=qualidade ENADE, V=vagas avaliadas/total, E=1−ICT | ↑ melhor |
| ICON | mun_com_Farmácia_Popular / mun_com_oferta_formativa | ↑ melhor |
| E | 1 − ICT | ↑ melhor |
| HHI | Σ(s_i²) para cada IES | ↓ mais disperso |

## Fontes

1. **Censo Educação Superior (INEP)** — vagas/cursos/IES/município: gov.br/inep
2. **Microdados ENADE/IDD (INEP)** — CC/ENADE/IDD por curso: mesma página
3. **Farmácia Popular (Min. Saúde)** — municípios credenciados: dados.gov.br
4. **e-MEC** — vagas autorizadas (cenário duplo): emec.mec.gov.br

## Design System

Cores: `--navy #16304F` · `--blue #2E5496` · `--gold #B07D22` · sem dados `#C9CDD2`  
Escalas divergentes: sempre **RdBu** (nunca RdYlGn — regra colorblind)  
`lang="pt-BR"` · justificação + hifenização · contraste WCAG AA
