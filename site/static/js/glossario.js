/* ============================================================
   GLOSSÁRIO INTERATIVO DE INDICADORES
   Fonte única de verdade; renderizado em todas as páginas.
   ============================================================ */
const GLOSSARIO = [
  { key:'ICT', sigla:'ICT', nome:'Índice de Concentração Territorial', cat:'Território',
    oque:'Mede o quanto a oferta de vagas está concentrada em poucos municípios. Quanto mais próximo de 1, mais a formação se concentra (geralmente na capital), deixando o interior descoberto.',
    escala:'0 a 1', dir:'menor', fonte:'Censo INEP', aliases:['ict'] },
  { key:'IAF', sigla:'IAF', nome:'Índice de Adequação Formativa', cat:'Qualidade',
    oque:'Combina qualidade (ENADE) e distribuição da oferta num único índice de 0 a 100. Mede se a formação disponível é adequada em quantidade e em qualidade.',
    escala:'0 a 100', dir:'maior', fonte:'ENADE + Censo INEP', aliases:['iaf'] },
  { key:'ICON', sigla:'ICON', nome:'Índice de Cobertura Assistencial', cat:'Território',
    oque:'Razão entre municípios com Farmácia Popular e municípios que já têm curso de Farmácia. Indica a presença da rede assistencial onde há formação.',
    escala:'contínuo', dir:'maior', fonte:'Min. Saúde', aliases:['icon ','cobertura assistencial'] },
  { key:'ICON_adj', sigla:'ICON-deserto', nome:'Cobertura de Desertos por Farmácia Popular', cat:'Território',
    oque:'Fração estimada dos desertos farmacêuticos (municípios SEM curso) que mesmo assim têm uma Farmácia Popular. Mede o potencial de ancorar estágios e práticas justamente onde não há curso. Estimativa conservadora (limite inferior).',
    escala:'0 a 1', dir:'maior', fonte:'Min. Saúde + Censo INEP', aliases:['icon-deserto','fp em desertos'] },
  { key:'E', sigla:'E', nome:'Equidade Territorial', cat:'Território',
    oque:'Complemento do ICT (E = 1 − ICT). Mede o quanto a oferta é distribuída de forma equilibrada pelo território. Maior = mais equânime.',
    escala:'0 a 1', dir:'maior', fonte:'Calculado', aliases:['equidade','e (equidade'] },
  { key:'vagas_total_real', sigla:'Vagas totais', nome:'Capacidade total (presencial + EaD)', cat:'Capacidade',
    oque:'Soma de todas as vagas anuais de Farmácia: presenciais mais EaD (atribuídas ao estado-sede da mantenedora). É a capacidade formativa real do estado.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP', aliases:['vagas totais'] },
  { key:'vagas_total', sigla:'Vagas presenciais', nome:'Vagas presenciais', cat:'Capacidade',
    oque:'Vagas anuais em cursos presenciais em funcionamento. Não inclui EaD.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP', aliases:['vagas presenciais','vagas (operante'] },
  { key:'vagas_ead', sigla:'Vagas EaD', nome:'Vagas a distância', cat:'Capacidade',
    oque:'Vagas anuais em cursos EaD, registradas na sede da mantenedora. Um único curso EaD pode atender dezenas de municípios via polos.',
    escala:'vagas/ano', dir:'contextual', fonte:'Censo INEP', aliases:['vagas ead'] },
  { key:'pct_ead', sigla:'% EaD', nome:'Participação da EaD na capacidade', cat:'Capacidade',
    oque:'Percentual das vagas que são a distância. Valores muito altos (acima de 70%) acendem alerta sobre a oferta de práticas presenciais essenciais à Farmácia.',
    escala:'0 a 100%', dir:'menor', fonte:'Censo INEP', aliases:['% ead','ead da capacidade'] },
  { key:'vagas_por_100k', sigla:'Vagas / 100 mil hab.', nome:'Densidade de vagas por habitante', cat:'Capacidade',
    oque:'Vagas totais por 100 mil habitantes. Normaliza a capacidade pela população, revelando excesso ou escassez relativa que o número absoluto esconde.',
    escala:'vagas/100k', dir:'contextual', fonte:'Censo INEP + IBGE', aliases:['100 mil hab','/100k','100k hab'] },
  { key:'populacao', sigla:'População', nome:'População residente estimada', cat:'Capacidade',
    oque:'Estimativa populacional do IBGE para o estado, usada como base para indicadores per capita.',
    escala:'habitantes', dir:'contextual', fonte:'IBGE', aliases:['populacao','população'] },
  { key:'taxa_retencao', sigla:'Taxa de conclusão', nome:'Conclusão (concluintes / matrículas)', cat:'Capacidade',
    oque:'Razão entre concluintes e matriculados no ano. É um retrato pontual (não acompanha uma coorte ao longo do tempo). Referência nacional em torno de 10%.',
    escala:'0 a 100%', dir:'maior', fonte:'Censo INEP', aliases:['conclusao','conclusão','conc./matr'] },
  { key:'mun_ead_only', sigla:'Municípios só com EaD', nome:'Municípios atendidos apenas por EaD', cat:'Território',
    oque:'Municípios que têm oferta de Farmácia exclusivamente a distância, sem nenhum curso presencial.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP', aliases:['so com ead','só com ead','municipios so com'] },
  { key:'ead_polos_municipios', sigla:'Municípios c/ polo EaD', nome:'Alcance territorial da EaD', cat:'Território',
    oque:'Número de municípios do estado que recebem oferta EaD via polo. Mostra a penetração real no território, que a contagem de vagas na sede esconde.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP', aliases:['polo ead','c/ polo'] },
  { key:'ead_polos_registros', sigla:'Polos EaD (registros)', nome:'Total de registros de polo EaD', cat:'Território',
    oque:'Número total de registros de polo EaD de Farmácia no estado. Um mesmo município pode ter mais de um polo (de instituições diferentes), por isso este número é maior que o de municípios com polo.',
    escala:'registros', dir:'contextual', fonte:'Censo INEP', aliases:['polos ead (registr','polo ead (registr'] },
  { key:'municipios_oferta', sigla:'Municípios c/ oferta', nome:'Municípios com oferta formativa', cat:'Território',
    oque:'Municípios com ao menos um curso de Farmácia em funcionamento.',
    escala:'municípios', dir:'contextual', fonte:'Censo INEP', aliases:['c/ oferta','com oferta'] },
  { key:'municipios_deserto', sigla:'Desertos', nome:'Desertos farmacêuticos', cat:'Território',
    oque:'Municípios sem nenhum curso de Farmácia. Quanto maior, menor o acesso local à formação.',
    escala:'municípios', dir:'menor', fonte:'Censo INEP', aliases:['deserto'] },
  { key:'n_ies', sigla:'IES', nome:'Instituições de Ensino Superior', cat:'Mercado',
    oque:'Número de instituições com curso de Farmácia no estado.',
    escala:'instituições', dir:'contextual', fonte:'Censo INEP', aliases:['ies com farmacia','ies com farmácia'] },
  { key:'HHI', sigla:'HHI (IES)', nome:'Índice Herfindahl-Hirschman por IES', cat:'Mercado',
    oque:'Mede a concentração do mercado entre instituições. 0 = muitas IES pequenas; 1 = uma só domina. Acima de 0,25 indica mercado concentrado.',
    escala:'0 a 1', dir:'menor', fonte:'Censo INEP', aliases:['hhi (por ies','hhi (ies'] },
  { key:'HHI_mantenedora', sigla:'HHI (mantenedora)', nome:'Concentração por grupo mantenedor', cat:'Mercado',
    oque:'Como o HHI, mas agrupando IES pelo mesmo dono (mantenedora). Revela conglomerados que controlam várias instituições — concentração que o HHI por IES não capta.',
    escala:'0 a 1', dir:'menor', fonte:'Censo INEP', aliases:['hhi (por manten','hhi (manten'] },
  { key:'CR2', sigla:'CR2', nome:'Razão de Concentração — 2 maiores', cat:'Mercado',
    oque:'Fatia das vagas detida pelas 2 maiores instituições do estado.',
    escala:'0 a 100%', dir:'menor', fonte:'Censo INEP', aliases:['cr2'] },
  { key:'CR10', sigla:'CR10', nome:'Razão de Concentração — 10 maiores', cat:'Mercado',
    oque:'Fatia das vagas detida pelas 10 maiores instituições do estado.',
    escala:'0 a 100%', dir:'menor', fonte:'Censo INEP', aliases:['cr10'] },
  { key:'CC', sigla:'CC', nome:'Conceito de Curso (ENADE)', cat:'Qualidade',
    oque:'Conceito médio dos cursos no ENADE, de 1 a 5. Avalia o desempenho dos concluintes na prova.',
    escala:'1 a 5', dir:'maior', fonte:'ENADE 2023', aliases:['cc (conc','cc (media','cc (média'] },
  { key:'ENADE', sigla:'ENADE', nome:'Conceito ENADE', cat:'Qualidade',
    oque:'Nota padronizada de desempenho dos concluintes no Exame Nacional de Desempenho dos Estudantes.',
    escala:'1 a 5', dir:'maior', fonte:'ENADE 2023', aliases:['enade (media','enade (média'] },
  { key:'IDD', sigla:'IDD', nome:'Indicador de Diferença de Desempenho', cat:'Qualidade',
    oque:'Mede o VALOR AGREGADO pelo curso: compara o desempenho final dos alunos com o esperado pelo perfil de ingresso. Isola o efeito do curso da qualidade de quem entrou. Escala contínua de 0 a 5.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / CPC 2023', aliases:['idd'] },
  { key:'CPC_cont', sigla:'CPC', nome:'Conceito Preliminar de Curso', cat:'Qualidade',
    oque:'Índice composto (0 a 5) que combina ENADE, IDD, corpo docente e infraestrutura. Visão geral da qualidade do curso.',
    escala:'0 a 5', dir:'maior', fonte:'INEP / CPC 2023', aliases:['cpc'] },
  { key:'pct_doc_doutores', sigla:'% Doutores', nome:'Docentes com doutorado', cat:'Qualidade',
    oque:'Proporção real de professores com título de doutor nos cursos avaliados, ponderada por concluintes. Quanto maior, mais qualificado o corpo docente. Média nacional ≈ 61%.',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC 2023', aliases:['doutores'] },
  { key:'pct_doc_mestres', sigla:'% Mestres+', nome:'Docentes com mestrado ou mais', cat:'Qualidade',
    oque:'Proporção de professores com titulação mínima de mestre (inclui os doutores). Indica a qualificação acadêmica geral do corpo docente. Média nacional ≈ 92%.',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC 2023', aliases:['mestres ou mais','mestres+','mestres'] },
  { key:'pct_doc_regime', sigla:'% Regime integral/parcial', nome:'Docentes em regime integral ou parcial', cat:'Qualidade',
    oque:'Proporção de professores contratados em regime de trabalho integral ou parcial (não horistas), o que favorece dedicação à pesquisa, orientação e permanência. Indicador de regime de trabalho do CPC.',
    escala:'0 a 100%', dir:'maior', fonte:'INEP / CPC 2023', aliases:['regime integral','regime de trabalho','integral/parcial'] },
  { key:'vagas_avaliadas', sigla:'Vagas avaliadas', nome:'Vagas em cursos avaliados', cat:'Qualidade',
    oque:'Vagas em cursos que participaram do ENADE — base sobre a qual os conceitos de qualidade se aplicam.',
    escala:'vagas', dir:'contextual', fonte:'ENADE 2023', aliases:['vagas avaliadas'] },
];

const DIR_META = {
  maior:      { txt:'Maior é melhor', icon:'▲', cor:'var(--swot-strength)' },
  menor:      { txt:'Menor é melhor', icon:'▼', cor:'var(--swot-strength)' },
  contextual: { txt:'Leitura contextual', icon:'◆', cor:'var(--text-muted)' },
};

function _normTxt(s) {
  return (s || '').toString().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function renderGlossario() {
  const root = document.getElementById('glossario-lista');
  if (!root) return;
  const cats = ['Território', 'Qualidade', 'Capacidade', 'Mercado'];
  let html = '';
  cats.forEach(cat => {
    const itens = GLOSSARIO.filter(g => g.cat === cat);
    if (!itens.length) return;
    html += `<div class="glossario-cat" data-cat="${cat}"><h3 class="glossario-cat-titulo">${cat}</h3><div class="glossario-cards">`;
    itens.forEach(g => {
      const dm = DIR_META[g.dir] || DIR_META.contextual;
      html += `
        <div class="gloss-card" id="gloss-${g.key}" data-busca="${_normTxt(g.sigla + ' ' + g.nome + ' ' + g.oque)}" tabindex="0"
             onclick="this.classList.toggle('aberto')" onkeypress="if(event.key==='Enter')this.classList.toggle('aberto')">
          <div class="gloss-head">
            <span class="gloss-sigla">${g.sigla}</span>
            <span class="gloss-nome">${g.nome}</span>
            <span class="gloss-toggle" aria-hidden="true">+</span>
          </div>
          <div class="gloss-body">
            <p>${g.oque}</p>
            <div class="gloss-meta">
              <span title="Escala / unidade">\u{1F4CF} ${g.escala}</span>
              <span style="color:${dm.cor}" title="Direção desejável">${dm.icon} ${dm.txt}</span>
              <span title="Fonte oficial">\u{1F3DB}️ ${g.fonte}</span>
            </div>
          </div>
        </div>`;
    });
    html += `</div></div>`;
  });
  root.innerHTML = html;
}

function filtrarGlossario(q) {
  const termo = _normTxt(q);
  document.querySelectorAll('.gloss-card').forEach(c => {
    const hit = !termo || c.dataset.busca.includes(termo);
    c.style.display = hit ? '' : 'none';
    if (termo && hit) c.classList.add('aberto');
    else if (!termo) c.classList.remove('aberto');
  });
  document.querySelectorAll('.glossario-cat').forEach(cat => {
    const algum = [...cat.querySelectorAll('.gloss-card')].some(c => c.style.display !== 'none');
    cat.style.display = algum ? '' : 'none';
  });
}

/* Salta para a verba do glossário e destaca */
function irParaGlossario(key) {
  const alvo = document.getElementById('gloss-' + key);
  if (!alvo) { document.getElementById('glossario') && document.getElementById('glossario').scrollIntoView({ behavior: 'smooth' }); return; }
  alvo.classList.add('aberto');
  alvo.scrollIntoView({ behavior: 'smooth', block: 'center' });
  alvo.classList.remove('flash'); void alvo.offsetWidth; alvo.classList.add('flash');
}

/* Auto-vincula cada cartão de KPI à sua verba do glossário pelo rótulo. */
function vincularKpisAoGlossario() {
  document.querySelectorAll('.kpi-card').forEach(card => {
    const label = card.querySelector('.kpi-label');
    if (!label) return;
    const txt = _normTxt(label.textContent);
    const g = GLOSSARIO.find(item => item.aliases.some(a => txt.includes(_normTxt(a))));
    if (!g) return;
    card.classList.add('kpi-clicavel');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.title = 'Clique para entender este indicador';
    card.addEventListener('click', () => irParaGlossario(g.key));
    card.addEventListener('keypress', e => { if (e.key === 'Enter') irParaGlossario(g.key); });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  renderGlossario();
  vincularKpisAoGlossario();
});
