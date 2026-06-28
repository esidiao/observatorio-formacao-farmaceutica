# Política de Segurança

## Natureza do projeto

O **Observatório Nacional da Formação Farmacêutica** é um site **estático** publicado
no GitHub Pages. Não há servidor de aplicação, banco de dados, autenticação de
usuários nem processamento de dados enviados por visitantes. Todo o conteúdo é
gerado em tempo de build a partir de fontes oficiais públicas (INEP, IBGE e
Ministério da Saúde). Por isso, a superfície de ataque é mínima.

## Medidas adotadas

- **HTTPS obrigatório** com HSTS (padrão do GitHub Pages).
- **Content-Security-Policy** restritiva: scripts, estilos e fontes apenas do
  próprio domínio; imagens e conexões limitadas a CARTO (mapas-base) e à API do
  IBGE (fallback de geometrias). `object-src 'none'`, `frame-ancestors 'none'`.
- **Referrer-Policy** `strict-origin-when-cross-origin`.
- **Bibliotecas hospedadas localmente** (Leaflet, Chart.js) — sem dependência de
  CDN de terceiros em tempo de execução.
- **Sem segredos no repositório**: nenhuma credencial, token ou chave versionada.
- **Registro de integridade**: hash SHA-256 de toda a obra em `data/registro_autoral.json`.

## Como relatar uma vulnerabilidade

Caso identifique uma falha de segurança, por favor **não abra uma issue pública**.
Entre em contato de forma reservada com o responsável pelo projeto:

- E-mail: sidiao@i9educar.com

Descreva o problema, os passos para reproduzi-lo e o impacto potencial.
Comprometemo-nos a responder o mais breve possível.
