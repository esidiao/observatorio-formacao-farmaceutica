/**
 * Observatório Nacional da Formação Farmacêutica
 * Lógica de mapa (Leaflet) e gráficos (Chart.js)
 */

/* ── Utilitários ─────────────────────────────────────────── */

/** Escala RdBu (invertida: baixo ICT = azul = bom) */
const RDBU = ['#2166AC','#4393C3','#92C5DE','#D1E5F0','#F7F7F7','#FDDBC7','#F4A582','#D6604D','#B2182B'];
const NODATA_COLOR = '#C9CDD2';

function corICT(val) {
  if (val === null || val === undefined) return NODATA_COLOR;
  // ICT: 0 = ótimo (azul), 1 = ruim (vermelho)
  const idx = Math.min(8, Math.floor(val * 9));
  return RDBU[idx];
}

function corIAF(val) {
  if (val === null || val === undefined) return NODATA_COLOR;
  // IAF: 0-100, maior = melhor → invertemos o RdBu
  const idx = Math.min(8, Math.floor((100 - val) / 100 * 9));
  return RDBU[idx];
}

function corICON(val) {
  if (val === null || val === undefined) return NODATA_COLOR;
  // ICON: maior = melhor; normaliza 0-15 → escala invertida
  const norm = Math.min(1, val / 15);
  const idx = Math.min(8, Math.floor((1 - norm) * 9));
  return RDBU[idx];
}

function getCor(indicador, val) {
  switch (indicador) {
    case 'ICT':  return corICT(val);
    case 'IAF':  return corIAF(val);
    case 'ICON': return corICON(val);
    default:     return corICT(val);
  }
}

function fmt(val, dec = 3) {
  if (val === null || val === undefined) return '<span class="nodata-cell">sem dados</span>';
  return Number(val).toFixed(dec);
}

function valClass(indicador, val) {
  if (val === null) return '';
  if (indicador === 'ICT') {
    return val < 0.5 ? 'val-bom' : val < 0.75 ? 'val-medio' : 'val-ruim';
  }
  if (indicador === 'IAF') {
    return val >= 40 ? 'val-bom' : val >= 25 ? 'val-medio' : 'val-ruim';
  }
  return '';
}

/* ── Mapa Nacional ───────────────────────────────────────── */

let mapaNacional = null;
let camadaEstados = null;
let indicadorAtual = 'ICT';

function iniciarMapaNacional(dadosUFs) {
  if (mapaNacional) return;

  mapaNacional = L.map('mapa-nacional', {
    zoomControl: true,
    scrollWheelZoom: false,
  });

  // Tile neutro (OpenStreetMap Carto Light)
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
    attribution: '© <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 12,
  }).addTo(mapaNacional);

  carregarEstados(dadosUFs);
}

async function carregarEstados(dadosUFs) {
  // Tenta local primeiro; fallback para IBGE API
  const urlLocal = (window._GEO_BASE || '') + 'static/geo/brasil.json';
  const urlIBGE = 'https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?resolucao=2&formato=application/vnd.geo%2Bjson';
  let geo;
  try {
    const r = await fetch(urlLocal, {cache: 'no-cache'});
    if (!r.ok) throw new Error('local indisponível');
    geo = await r.json();
  } catch (_) {
    try {
      const r = await fetch(urlIBGE);
      geo = await r.json();
    } catch (e) {
      console.warn('IBGE API indisponível — mapa sem geometrias:', e);
      return;
    }
  }

  // Injetar dados do observatório em cada feature
  geo.features.forEach(f => {
    const sigla = f.properties?.codarea ? codigoParaSigla(f.properties.codarea) : null;
    f.properties._sigla = sigla;
    f.properties._dados = sigla ? dadosUFs[sigla] : null;
  });

  camadaEstados = L.geoJSON(geo, {
    style: feature => ({
      fillColor: getCor(indicadorAtual, feature.properties._dados?.[indicadorAtual]),
      fillOpacity: 0.78,
      color: '#fff',
      weight: 1,
    }),
    onEachFeature: (feature, layer) => {
      const d = feature.properties._dados;
      const sigla = feature.properties._sigla || '?';

      const popup = d
        ? `<b>${sigla}</b><br>ICT: ${fmt(d.ICT, 3)}<br>IAF: ${fmt(d.IAF, 1)}<br>ICON: ${fmt(d.ICON, 1)}`
        : `<b>${sigla}</b><br><i>sem dados</i>`;

      layer.bindTooltip(popup, { sticky: true });

      layer.on('click', () => {
        const pagina = `uf/${sigla}.html`;
        window.location.href = pagina;
      });

      layer.on('mouseover', () => layer.setStyle({ fillOpacity: 0.95, weight: 2 }));
      layer.on('mouseout', () => camadaEstados.resetStyle(layer));
    },
  }).addTo(mapaNacional);

  mapaNacional.fitBounds(camadaEstados.getBounds(), { padding: [10, 10] });
}

function atualizarCorMapa(indicador) {
  indicadorAtual = indicador;
  if (!camadaEstados) return;
  camadaEstados.eachLayer(layer => {
    const val = layer.feature.properties._dados?.[indicador];
    layer.setStyle({
      fillColor: getCor(indicador, val),
      fillOpacity: 0.78,
    });
  });
}

/* ── Mapa UF (municípios) ────────────────────────────────── */

let mapaUF = null;

async function iniciarMapaUF(codigoIBGE, municipiosComOferta) {
  if (mapaUF) return;

  mapaUF = L.map('mapa-uf', { scrollWheelZoom: false });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
    attribution: '© CARTO',
    subdomains: 'abcd',
    maxZoom: 14,
  }).addTo(mapaUF);

  const urlLocal = (window._GEO_BASE || '') + `static/geo/estados/${codigoIBGE}.json`;
  const urlIBGE = `https://servicodados.ibge.gov.br/api/v3/malhas/estados/${codigoIBGE}?resolucao=5&formato=application/vnd.geo%2Bjson`;
  let geo;
  try {
    const r = await fetch(urlLocal, {cache: 'no-cache'});
    if (!r.ok) throw new Error('local indisponível');
    geo = await r.json();
  } catch (_) {
    try {
      const r = await fetch(urlIBGE);
      geo = await r.json();
    } catch (e) {
      console.warn('IBGE API indisponível para municípios:', e);
      return;
    }
  }

  // Normaliza nomes para match (sem acento, maiúsculo)
  const ofertaSet = new Set(municipiosComOferta.map(normalizar));

  L.geoJSON(geo, {
    style: feature => {
      const nome = normalizar(feature.properties?.NM_MUN || feature.properties?.nome || '');
      const temOferta = ofertaSet.has(nome);
      return {
        fillColor: temOferta ? '#2E5496' : '#C9CDD2',
        fillOpacity: 0.75,
        color: '#fff',
        weight: 0.5,
      };
    },
    onEachFeature: (feature, layer) => {
      const nome = feature.properties?.NM_MUN || feature.properties?.nome || '?';
      const temOferta = ofertaSet.has(normalizar(nome));
      layer.bindTooltip(
        `<b>${nome}</b><br>${temOferta ? '✓ Com oferta formativa' : '○ Deserto farmacêutico'}`,
        { sticky: true }
      );
    },
  }).addTo(mapaUF);

  mapaUF.fitBounds(mapaUF.getBounds?.() ?? [[0,0],[0,0]], { padding: [8, 8] });
}

/* ── Helpers ─────────────────────────────────────────────── */

function normalizar(s) {
  return String(s)
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .trim();
}

// Mapa código IBGE → sigla UF
const COD_PARA_SIGLA = {
  '11':'RO','12':'AC','13':'AM','14':'RR','15':'PA',
  '16':'AP','17':'TO','21':'MA','22':'PI','23':'CE',
  '24':'RN','25':'PB','26':'PE','27':'AL','28':'SE',
  '29':'BA','31':'MG','32':'ES','33':'RJ','35':'SP',
  '41':'PR','42':'SC','43':'RS','50':'MS','51':'MT',
  '52':'GO','53':'DF',
};

const SIGLA_PARA_COD = Object.fromEntries(
  Object.entries(COD_PARA_SIGLA).map(([k,v]) => [v,k])
);

function codigoParaSigla(cod) {
  // codarea pode ser string de 7 dígitos (código de município) ou 2 (UF)
  const s = String(cod).padStart(2, '0');
  return COD_PARA_SIGLA[s] || COD_PARA_SIGLA[s.slice(0,2)] || null;
}

/* ── Exportar dados (CSV/JSON) ───────────────────────────── */

function exportarCSV(dados, filename) {
  const ufs = Object.entries(dados);
  const cols = ['UF','vagas_total','vagas_capital','municipios_oferta','municipios_deserto',
                 'ICT','IAF','ICON','E','HHI','CR2','CR10'];
  const linhas = [cols.join(';')];
  ufs.forEach(([uf, d]) => {
    linhas.push(cols.map(c => c === 'UF' ? uf : (d[c] ?? '')).join(';'));
  });
  baixarArquivo(linhas.join('\n'), filename, 'text/csv;charset=utf-8');
}

function exportarJSON(dados, filename) {
  baixarArquivo(JSON.stringify(dados, null, 2), filename, 'application/json');
}

function baixarArquivo(conteudo, filename, tipo) {
  const blob = new Blob([conteudo], { type: tipo });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

/* ── Tabela comparativa (home) ───────────────────────────── */

function renderTabelaNacional(dadosUFs, tbody, indicadorDestaque) {
  const ufs = Object.entries(dadosUFs).sort((a, b) => {
    const va = a[1][indicadorDestaque] ?? Infinity;
    const vb = b[1][indicadorDestaque] ?? Infinity;
    return va - vb; // ICT: menor = melhor
  });

  tbody.innerHTML = '';
  ufs.forEach(([sigla, d]) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><a href="uf/${sigla}.html"><span class="uf-tag">${sigla}</span></a></td>
      <td>${(d.vagas_total ?? 0).toLocaleString('pt-BR')}</td>
      <td class="${valClass('ICT', d.ICT)}">${fmt(d.ICT, 3)}</td>
      <td class="${valClass('IAF', d.IAF)}">${fmt(d.IAF, 1)}</td>
      <td>${fmt(d.ICON, 1)}</td>
      <td>${d.municipios_oferta ?? '–'}</td>
      <td>${d.municipios_deserto ?? '–'}</td>
      <td>${fmt(d.HHI, 4)}</td>
    `;
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => { window.location.href = `uf/${sigla}.html`; });
    tbody.appendChild(tr);
  });
}
