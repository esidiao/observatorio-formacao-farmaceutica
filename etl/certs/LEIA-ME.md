# Certificados intermediários versionados

Certificados **públicos** de autoridades certificadoras intermediárias, usados só
para validar servidores que enviam a cadeia TLS incompleta. Não há segredo aqui.

## Por que isto existe

Em 21/09/2026 o `download.inep.gov.br` renovou o certificado (`*.inep.gov.br`,
emitido por `RNP ICPEdu GR46 OV TLS CA 2025`) e passou a enviar **só o certificado
do site, sem o intermediário**. Navegadores e o Windows buscam o intermediário
sozinhos (extensão AIA); o `requests`/OpenSSL com `certifi` não busca, e a
verificação falha com `SSLError`.

O efeito foi silencioso: `check_fontes()` trata falha de rede como INDETERMINADO,
que só emite um `::warning::` — o CI continua verde, o passo "Criar issue" é pulado
e ninguém é avisado quando o Censo novo sai. Detectado na auditoria de 2026-11-23.

A correção NÃO desliga a verificação (`verify=False` é proibido neste projeto).
Em vez disso, `etl/pipeline.py` monta um bundle = `certifi` + os `.pem` desta
pasta e o usa **apenas** para os hosts listados em `HOSTS_CADEIA_INCOMPLETA`.
A raiz (`GlobalSign Root R46`) já está no `certifi`; falta só o elo do meio.

## Conteúdo

| Arquivo | Assunto | Emissor | Validade | SHA-256 (DER) |
|---|---|---|---|---|
| `rnp-icpedu-gr46-ov-tls-ca-2025.pem` | `RNP ICPEdu GR46 OV TLS CA 2025` | `GlobalSign Root R46` | 19/11/2025 → **19/11/2030** | `E10747D4DA7BAB09CBA9952F019D3534CB9FBA070BF13D8791B1699CD2FF59DD` |

Origem: campo *CA Issuers* (AIA) do certificado do INEP —
`http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt`.
`tests/test_check_fontes.py` confere o SHA-256 e avisa quando a validade se aproxima.

## Como renovar (se o INEP trocar de emissor)

Sintoma: `check_fontes` volta a dar INDETERMINADO com
`SSLError — cadeia do INEP não validou`.

```bash
# 1. certificado atual do servidor e o URL do intermediário
echo | openssl s_client -connect download.inep.gov.br:443 -servername download.inep.gov.br -showcerts 2>/dev/null \
  | awk '/BEGIN CERT/{f=1} f{print} /END CERT/{exit}' > folha.pem
openssl x509 -in folha.pem -noout -text | grep "CA Issuers"

# 2. baixar o intermediário e converter para PEM
curl -s -o inter.crt "<URL do CA Issuers>"
openssl x509 -inform DER -in inter.crt -out inter.pem

# 3. PROVAR que a cadeia fecha contra a raiz do certifi antes de versionar
openssl verify -CAfile "$(python -c 'import certifi;print(certifi.where())')" -untrusted inter.pem folha.pem
#   → deve imprimir "OK"
```

Depois: copie `inter.pem` para esta pasta, atualize a tabela acima e o
fingerprint em `tests/test_check_fontes.py`.
