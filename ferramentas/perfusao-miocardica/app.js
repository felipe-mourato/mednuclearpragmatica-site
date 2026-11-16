/* Cintilografia de perfusão miocárdica — interface.
 *
 * Este arquivo só cuida da tela: carregar o núcleo, receber arquivos,
 * capturar mouse e toque, desenhar o que o núcleo devolve e copiar ou
 * baixar arquivos. Todo cálculo (leitura das projeções, geometria,
 * controle de qualidade, filtro, reconstrução, eixos, cortes, mapa polar,
 * escores, exportações e laudo) acontece no núcleo em Python (pacote
 * mnp-nucleo), rodando no navegador pelo Pyodide.
 */
'use strict';

(() => {
  // Versão travada do Pyodide (Python + NumPy no navegador), servida pelo CDN.
  // Para atualizar: troque o número, teste a ferramenta e registre no README.
  const PYODIDE_VERSAO = '0.29.5';
  const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
  const PACOTES_URL = new URL('/ferramentas/_pacotes/', location.href);
  const TIPOS_CORTE = [
    ['SA', 'Eixo curto', 'do ápice para a base'],
    ['VLA', 'Eixo longo vertical', 'do septo para a lateral'],
    ['HLA', 'Eixo longo horizontal', 'de inferior para anterior'],
  ];

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const num = (v, casas = 1) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }));

  let pyodide = null;
  let sessao = null;
  let estado = null;
  let versoes = {};
  let passo = 0;
  let qcArquivo = null;
  let qcDados = null;
  let qcAngulo = 0;
  let qcIntervalo = null;
  let qcLinha = null;
  let cineTimer = null;
  let estudoEixo = 'estresse';
  const cortePorEstudo = {};
  let pincel = 0;
  let rotulosPolar = 'escores';
  let resultados = null;
  const exibicao = new Map(); // chave -> {nivel, largura, invertido}
  const visores = new Map();

  // ----------------------------------------------------------------- núcleo
  function cmd(comando) {
    const r = JSON.parse(sessao.executar(JSON.stringify(comando)));
    if (r.estado) estado = r.estado;
    return r;
  }
  function bytesDe(retorno) {
    if (retorno instanceof Uint8Array) return retorno;
    try { return retorno.toJs(); } finally { retorno.destroy?.(); }
  }
  function chamarBytes(metodo, pedido) { return bytesDe(sessao[metodo](JSON.stringify(pedido))); }
  function mensagemPython(erro) {
    const texto = String(erro?.message || erro);
    const linhas = texto.trim().split('\n');
    return (linhas[linhas.length - 1] || texto).replace(/^[\w.]*(Error|ErroSessao|ErroDicom):\s*/, '');
  }
  function pintar(canvas, rgba, w, h) {
    canvas.width = w;
    canvas.height = h;
    canvas.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, rgba.byteLength), w, h), 0, 0);
  }
  function imagemColorida(pedido, w, h, classe = '') {
    const c = document.createElement('canvas');
    c.className = `colorida ${classe}`;
    try { pintar(c, chamarBytes('imagem', pedido), w, h); } catch (erro) { console.error(erro); }
    return c;
  }

  // ----------------------------------------------------------- carregamento
  function etapa(nome, situacao) {
    const li = $(`[data-etapa="${nome}"]`);
    li.classList.remove('ativa', 'feita');
    li.classList.add(situacao);
  }
  function progresso(p) {
    const barra = $('.barra');
    barra.setAttribute('aria-valuenow', String(p));
    barra.firstElementChild.style.width = `${p}%`;
  }
  function carregarScript(src) {
    return new Promise((ok, falha) => {
      const s = document.createElement('script');
      s.src = src;
      s.crossOrigin = 'anonymous';
      s.onload = ok;
      s.onerror = () => falha(new Error('não foi possível baixar o Pyodide do CDN'));
      document.head.appendChild(s);
    });
  }
  async function iniciar() {
    $$('[data-versao-pyodide]').forEach((e) => { e.textContent = PYODIDE_VERSAO; });
    try {
      etapa('pyodide', 'ativa'); progresso(4);
      if (!window.loadPyodide) await carregarScript(`${PYODIDE_URL}pyodide.js`);
      progresso(15);
      pyodide = await window.loadPyodide({ indexURL: PYODIDE_URL });
      etapa('pyodide', 'feita'); progresso(55);
      etapa('numpy', 'ativa');
      await pyodide.loadPackage('numpy');
      etapa('numpy', 'feita'); progresso(75);
      etapa('pacotes', 'ativa');
      const resp = await fetch(new URL('pacotes.json', PACOTES_URL), { cache: 'no-cache' });
      if (!resp.ok) throw new Error(`manifesto de pacotes indisponível (HTTP ${resp.status})`);
      const manifesto = await resp.json();
      await pyodide.loadPackage(manifesto.pacotes.map((p) => new URL(p.caminho, PACOTES_URL).href));
      etapa('pacotes', 'feita'); progresso(92);
      etapa('iniciar', 'ativa');
      pyodide.runPython('from mnp_nucleo.perfusao.sessao import Sessao\nsessao = Sessao()');
      sessao = pyodide.globals.get('sessao');
      versoes = JSON.parse(pyodide.runPython('import json, mnp_nucleo\njson.dumps(mnp_nucleo.versoes())'));
      versoes.pyodide = PYODIDE_VERSAO;
      if (manifesto.nucleo && manifesto.nucleo !== versoes.mnp_nucleo) {
        throw new Error(`versão do núcleo inesperada (${versoes.mnp_nucleo}; esperada ${manifesto.nucleo})`);
      }
      etapa('iniciar', 'feita'); progresso(100);
      $('[data-versoes]').textContent = `Núcleo mnp-nucleo ${versoes.mnp_nucleo} · pydicom ${versoes.pydicom} · NumPy ${versoes.numpy} · Python ${versoes.python} · Pyodide ${PYODIDE_VERSAO}`;
      cmd({ acao: 'estado' });
      $('#carregamento').hidden = true;
      $('#ferramenta').hidden = false;
      irPara(0);
    } catch (erro) {
      console.error(erro);
      $('[data-erro-carga]').textContent = `Detalhe: ${mensagemPython(erro)}.`;
      $('.erro-carga').hidden = false;
      $$('.etapas-carga li.ativa').forEach((li) => li.classList.remove('ativa'));
    }
  }

  // ------------------------------------------------------------------ passos
  function liberado(i) {
    if (!estado) return i === 0;
    const v = estado.validacao;
    if (i === 0) return true;
    if (i <= 3) return !v.arquivos;
    return !v.eixos;
  }

  // Tarefas demoradas (reconstrução): mostra a mensagem antes de travar a tela.
  function depoisDePintar(fn) { requestAnimationFrame(() => setTimeout(fn, 20)); }

  function irPara(i) {
    if (!liberado(i)) return;
    pararCine();
    if (i >= 2 && !estado.reconstruido) {
      passo = i;
      mostrarPasso();
      $('[data-status-recon]').textContent = 'Reconstruindo…';
      $(`[data-painel="${i}"]`).classList.add('ocupado');
      depoisDePintar(() => {
        const r = cmd({ acao: 'reconstruir' });
        $(`[data-painel="${i}"]`).classList.remove('ocupado');
        if (!r.ok) avisar(r.erro);
        render();
      });
      return;
    }
    passo = i;
    mostrarPasso();
    render();
  }

  function mostrarPasso() {
    $$('.passo').forEach((p) => { p.hidden = Number(p.dataset.painel) !== passo; });
    if (passo > 0) $('.passos').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function render() {
    $$('.passos button').forEach((b) => {
      const i = Number(b.dataset.passo);
      b.disabled = !liberado(i);
      b.classList.toggle('feito', i < passo);
      if (i === passo) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    });
    $$('[data-ir]').forEach((b) => { const alvo = Number(b.dataset.ir); if (alvo > passo) b.disabled = !liberado(alvo); });
    const v = estado?.validacao || {};
    $('[data-validacao="0"]').textContent = estado?.arquivos.length ? v.arquivos || '' : '';
    $('[data-validacao="3"]').textContent = v.eixos || '';
    visores.clear();
    [renderArquivos, renderQC, renderRecon, renderEixos, renderCortes, renderPasso6, renderLaudo][passo]();
  }

  function blocoAvisos(seletor, extras = []) {
    const avisos = [...(estado.avisos || []), ...extras];
    $(seletor).innerHTML = avisos.length
      ? `<div class="alerta" role="status"><strong>Confira:</strong><ul>${avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>`
      : '';
  }
  function avisar(texto) { const alvo = $(`[data-validacao="${passo}"]`); if (alvo) alvo.textContent = texto; }
  const arquivoPorId = (id) => estado.arquivos.find((a) => a.id === id);
  const estudoPorNome = (e) => estado.estudos.find((x) => x.estudo === e);

  // ----------------------------------------------------------------- visor
  class Visor {
    /* Imagem em cinza com janela ajustável (botão do meio) e camada SVG.
       pedido(): o que pedir ao núcleo; sobre(): SVG por cima;
       aoApertar/aoMover/aoSoltar(ponto): desenho com o botão esquerdo. */
    constructor({ chave, largura, altura, pedido, padrao = null, sobre = null, rotulo = '', aoApertar = null, aoMover = null, aoSoltar = null }) {
      Object.assign(this, { chave, largura, altura, pedido, padrao, sobre, aoApertar, aoMover, aoSoltar });
      this.semJanela = !padrao; // sem janela própria: o núcleo usa o máximo da imagem
      this.el = document.createElement('div');
      this.el.className = `visor ${aoApertar ? 'desenho' : ''}`;
      this.el.style.aspectRatio = `${largura} / ${altura}`;
      this.el.setAttribute('role', 'img');
      this.el.setAttribute('aria-label', rotulo);
      this.canvas = document.createElement('canvas');
      this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      this.svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
      this.svg.setAttribute('preserveAspectRatio', 'none');
      this.el.append(this.canvas, this.svg);
      this.acao = null;
      this.quadroPendente = false;
      this.ligar();
      visores.set(chave + Math.random(), this);
    }
    janela() {
      if (!exibicao.has(this.chave)) exibicao.set(this.chave, { ...this.padrao, invertido: false });
      return exibicao.get(this.chave);
    }
    desenhar() {
      const j = this.janela();
      const janela = this.semJanela ? {} : { nivel: j.nivel, largura: j.largura };
      try {
        pintar(this.canvas, chamarBytes('imagem', { ...this.pedido(), ...janela, invertido: j.invertido }), this.largura, this.altura);
      } catch (erro) { console.error(erro); }
      this.sobrepor();
    }
    sobrepor() { this.svg.innerHTML = this.sobre ? this.sobre() : ''; }
    ponto(e) {
      const r = this.svg.getBoundingClientRect();
      return [((e.clientX - r.left) / r.width) * this.largura, ((e.clientY - r.top) / r.height) * this.altura];
    }
    agendar(fn) {
      this.pendente = fn;
      if (this.quadroPendente) return;
      this.quadroPendente = true;
      requestAnimationFrame(() => { this.quadroPendente = false; const f = this.pendente; this.pendente = null; f?.(); });
    }
    ligar() {
      const el = this.el;
      el.addEventListener('contextmenu', (e) => { e.preventDefault(); abrirMenu(e, this); });
      el.addEventListener('auxclick', (e) => { if (e.button === 1 && e.detail === 2) { exibicao.delete(this.chave); redesenhar(this.chave); } });
      el.addEventListener('pointerdown', (e) => {
        if (e.button === 2) return;
        if (e.button === 1) {
          e.preventDefault();
          if (this.semJanela) return;
          const j = this.janela();
          this.acao = { tipo: 'janela', x: e.clientX, y: e.clientY, nivel: j.nivel, largura: j.largura };
          el.classList.add('janela');
          el.setPointerCapture(e.pointerId);
          return;
        }
        if (e.button !== 0 || !this.aoApertar) return;
        e.preventDefault();
        this.acao = { tipo: 'desenho' };
        this.aoApertar(this.ponto(e));
        el.setPointerCapture(e.pointerId);
      });
      el.addEventListener('pointermove', (e) => {
        const a = this.acao;
        if (a?.tipo === 'janela') {
          const dx = e.clientX - a.x;
          const dy = e.clientY - a.y;
          this.agendar(() => {
            const r = cmd({ acao: 'janela_arraste', nivel: a.nivel, largura: a.largura, dx, dy, faixa: this.padrao.faixa });
            Object.assign(this.janela(), { nivel: r.nivel, largura: r.largura });
            redesenhar(this.chave);
          });
        } else if (a?.tipo === 'desenho' && this.aoMover) {
          const p = this.ponto(e);
          this.agendar(() => this.aoMover(p));
        }
      });
      const terminar = (e) => {
        const a = this.acao;
        this.acao = null;
        this.pendente = null;
        el.classList.remove('janela');
        if (a?.tipo === 'desenho' && this.aoSoltar) this.aoSoltar(this.ponto(e));
      };
      el.addEventListener('pointerup', terminar);
      el.addEventListener('pointercancel', terminar);
    }
  }
  function redesenhar(chave) { for (const v of visores.values()) if (v.chave === chave) v.desenhar(); }

  let visorDoMenu = null;
  function abrirMenu(e, visor) {
    visorDoMenu = visor;
    const menu = $('.menu-contexto');
    const inv = visor.janela().invertido;
    $('[data-cinza="normal"]', menu).setAttribute('aria-checked', String(!inv));
    $('[data-cinza="invertida"]', menu).setAttribute('aria-checked', String(inv));
    menu.hidden = false;
    menu.style.left = `${Math.min(e.clientX, innerWidth - menu.offsetWidth - 8)}px`;
    menu.style.top = `${Math.min(e.clientY, innerHeight - menu.offsetHeight - 8)}px`;
    $('button', menu).focus();
  }
  function fecharMenu() { $('.menu-contexto').hidden = true; visorDoMenu = null; }

  // ----------------------------------------------------------- passo 1
  function renderArquivos() {
    const erros = estado.erros;
    $('[data-erros]').innerHTML = erros.length
      ? `<div class="alerta alerta--erro" role="alert"><strong>Alguns arquivos não foram lidos.</strong><ul>${erros.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
         <div class="linha-acoes"><button type="button" class="mnp-btn mnp-btn--pequeno" data-acao="fechar-erros">Fechar</button></div></div>`
      : '';
    blocoAvisos('[data-avisos-0]');
    const lista = $('[data-arquivos]');
    lista.innerHTML = '';
    for (const a of estado.arquivos) lista.appendChild(cartaoArquivo(a));
    $('[data-acao="limpar"]').hidden = estado.arquivos.length === 0;
  }

  function cartaoArquivo(a) {
    const div = document.createElement('article');
    div.className = `slot ${a.tipo === 'ignorar' ? 'slot--ignorado' : ''}`;
    const opcoes = estado.tipos
      .filter((t) => a.gated || !t.valor.startsWith('gated'))
      .map((t) => `<option value="${t.valor}" ${t.valor === a.tipo ? 'selected' : ''}>${esc(t.rotulo)}</option>`).join('');
    const i = a.info;
    const g = a.info_gated || {};
    div.innerHTML = `
      <div class="miniatura"></div>
      <div>
        <div class="arquivo-nome"><span>${esc(a.nome)}</span><button type="button" data-remover="${esc(a.id)}" aria-label="Remover o arquivo ${esc(a.nome)}" title="Remover o arquivo">×</button></div>
        <label class="campo campo-incidencia">Aquisição <select data-tipo="${esc(a.id)}">${opcoes}</select></label>
        <div class="arquivo-dados">
          <span>${esc([i.fabricante, i.modelo].filter(Boolean).join(' ') || 'fabricante não informado')}</span>
          <span>Projeções <b>${i.projecoes}</b> em <b>${num(i.arco_graus, 0)}°</b></span>
          <span>Matriz <b>${esc(i.matriz)}</b></span>
          <span>Pixel <b>${num(i.pixel_mm, 2)} mm</b></span>
          ${i.duracao_vista_s ? `<span>Por vista <b>${num(i.duracao_vista_s, 1)} s</b></span>` : ''}
          <span>Contagens <b>${esc(a.contagens)}</b></span>
          ${a.gated ? `<span>Gated <b>${a.dims.intervalos} intervalos</b></span>` : ''}
          ${g.batimentos_rejeitados !== undefined ? `<span>Rejeitados <b>${g.batimentos_rejeitados}${g.percentual_rejeitado !== undefined ? ` (${num(g.percentual_rejeitado, 1)}%)` : ''}</b></span>` : ''}
          <span>${esc(/JPEG/.test(i.sintaxe) ? 'JPEG sem perdas' : 'sem compressão')}</span>
        </div>
        ${a.avisos.map((x) => `<p class="nota">${esc(x)}</p>`).join('')}
      </div>`;
    const v = new Visor({
      chave: `proj:${a.id}`, largura: a.dims.colunas, altura: a.dims.linhas, padrao: a.janela, rotulo: `Projeção de ${a.nome}`,
      pedido: () => ({ fonte: 'projecao', arquivo: a.id, indice: Math.floor(a.dims.angulos / 2) }),
    });
    $('.miniatura', div).appendChild(v.el);
    v.desenhar();
    return div;
  }

  async function receberArquivos(lista) {
    const arquivos = Array.from(lista || []);
    if (!arquivos.length) return;
    cmd({ acao: 'limpar_erros' });
    const zona = $('.zona-titulo');
    const original = zona.textContent;
    for (const [i, f] of arquivos.entries()) {
      zona.textContent = `Lendo ${i + 1} de ${arquivos.length}: ${f.name}`;
      await new Promise((ok) => depoisDePintar(ok));
      const dados = new Uint8Array(await f.arrayBuffer());
      estado = JSON.parse(sessao.adicionar_arquivo(f.name, dados)).estado;
    }
    zona.textContent = original;
    render();
  }

  // ----------------------------------------------------------- passo 2
  function pararCine() {
    if (cineTimer) { clearInterval(cineTimer); cineTimer = null; }
    const b = $('[data-acao="cine"]');
    if (b) { b.setAttribute('aria-pressed', 'false'); b.textContent = 'Reproduzir'; }
  }

  function renderQC() {
    const usados = estado.arquivos.filter((a) => a.tipo !== 'ignorar');
    if (!usados.find((a) => a.id === qcArquivo)) { qcArquivo = usados[0]?.id; qcDados = null; qcLinha = null; qcIntervalo = null; }
    $('[data-abas-qc]').innerHTML = usados.map((a) => `<button type="button" role="tab" data-aba-qc="${esc(a.id)}" aria-selected="${a.id === qcArquivo}">${esc(estado.tipos.find((t) => t.valor === a.tipo).rotulo)}</button>`).join('');
    const a = arquivoPorId(qcArquivo);
    if (!a) return;
    if (!qcDados || qcDados.arquivo !== a.id) {
      qcDados = cmd({ acao: 'qc', arquivo: a.id }).qc;
      qcAngulo = Math.min(qcAngulo, a.dims.angulos - 1);
    }
    if (qcLinha === null) qcLinha = qcDados.linha_sugerida;
    const angulo = $('[data-angulo]');
    angulo.max = String(a.dims.angulos - 1);
    angulo.value = String(qcAngulo);
    const linha = $('[data-linha]');
    linha.max = String(a.dims.linhas - 1);
    linha.value = String(qcLinha);
    $('[data-linha-texto]').textContent = `· linha ${qcLinha + 1}`;
    $('[data-controle-intervalo]').hidden = !a.gated;
    if (a.gated) {
      $('[data-intervalo]').innerHTML = `<option value="">Soma dos intervalos</option>${Array.from({ length: a.dims.intervalos }, (_, k) => `<option value="${k}" ${qcIntervalo === k ? 'selected' : ''}>Intervalo ${k + 1}</option>`).join('')}`;
    }
    const cine = new Visor({
      chave: `cine:${a.id}`, largura: a.dims.colunas, altura: a.dims.linhas, padrao: a.janela, rotulo: 'Projeção',
      pedido: () => ({ fonte: 'projecao', arquivo: a.id, indice: qcAngulo, intervalo: qcIntervalo }),
      sobre: () => `<line class="guia" x1="0" x2="${a.dims.colunas}" y1="${qcLinha + 0.5}" y2="${qcLinha + 0.5}"/>`,
      aoApertar: (p) => { qcLinha = Math.max(0, Math.min(a.dims.linhas - 1, Math.floor(p[1]))); atualizarSino(); },
      aoMover: (p) => { qcLinha = Math.max(0, Math.min(a.dims.linhas - 1, Math.floor(p[1]))); atualizarSino(); },
    });
    const sino = new Visor({
      chave: `sino:${a.id}`, largura: a.dims.colunas, altura: a.dims.angulos, padrao: a.janela, rotulo: 'Sinograma',
      pedido: () => ({ fonte: 'sinograma', arquivo: a.id, linha: qcLinha }),
      sobre: () => `<line class="guia" x1="0" x2="${a.dims.colunas}" y1="${qcAngulo + 0.5}" y2="${qcAngulo + 0.5}"/>`,
    });
    const lino = new Visor({
      chave: `lino:${a.id}`, largura: a.dims.angulos, altura: a.dims.linhas, rotulo: 'Linograma',
      pedido: () => ({ fonte: 'linograma', arquivo: a.id }),
      sobre: () => `<line class="guia" y1="0" y2="${a.dims.linhas}" x1="${qcAngulo + 0.5}" x2="${qcAngulo + 0.5}"/>`,
    });
    for (const [sel, v] of [['[data-visor-cine]', cine], ['[data-visor-sino]', sino], ['[data-visor-lino]', lino]]) {
      $(sel).innerHTML = '';
      $(sel).appendChild(v.el);
      v.desenhar();
    }
    atualizarRotuloCine(a);
    $('[data-grafico-projecoes]').innerHTML = graficoLinha(qcDados.angulos, qcDados.contagens_projecao, 'Ângulo (graus)', 'Contagens', qcAngulo);
    renderQCGated(a);
  }

  function atualizarRotuloCine(a) {
    $('[data-angulo-texto]').textContent = `${qcAngulo + 1} de ${a.dims.angulos} · ${num(qcDados.angulos[qcAngulo], 1)}°`;
    $('[data-rotulo-cine]').textContent = `Projeção · ${num(qcDados.angulos[qcAngulo], 1)}°${qcIntervalo !== null ? ` · intervalo ${qcIntervalo + 1}` : ''}`;
  }

  function atualizarSino() {
    $('[data-linha]').value = String(qcLinha);
    $('[data-linha-texto]').textContent = `· linha ${qcLinha + 1}`;
    for (const v of visores.values()) {
      if (v.chave.startsWith('sino:')) v.desenhar();
      if (v.chave.startsWith('cine:')) v.sobrepor();
    }
  }

  function moverAngulo(i) {
    const a = arquivoPorId(qcArquivo);
    qcAngulo = (i + a.dims.angulos) % a.dims.angulos;
    $('[data-angulo]').value = String(qcAngulo);
    for (const v of visores.values()) {
      if (v.chave.startsWith('cine:')) v.desenhar();
      else v.sobrepor();
    }
    atualizarRotuloCine(a);
    $('[data-grafico-projecoes]').innerHTML = graficoLinha(qcDados.angulos, qcDados.contagens_projecao, 'Ângulo (graus)', 'Contagens', qcAngulo);
  }

  function renderQCGated(a) {
    const alvo = $('[data-qc-gated]');
    if (!a.gated || !qcDados.intervalos) { alvo.innerHTML = ''; return; }
    const g = qcDados.info_gated || {};
    const campos = [
      ['batimentos_aceitos', 'Batimentos aceitos'], ['batimentos_rejeitados', 'Batimentos rejeitados'], ['percentual_rejeitado', 'Rejeitados (%)'],
      ['frequencia_cardiaca', 'Frequência cardíaca (bpm)'], ['intervalo_rr_nominal_ms', 'R-R nominal (ms)'], ['rr_minimo_ms', 'R-R mínimo aceito (ms)'],
      ['rr_maximo_ms', 'R-R máximo aceito (ms)'], ['rejeicao_batimentos', 'Rejeição de batimentos'], ['tipo_divisao', 'Divisão do ciclo'],
    ].filter(([k]) => g[k] !== undefined);
    const pct = qcDados.intervalos.percentual_da_media;
    alvo.innerHTML = `
      <h3 class="subtitulo">Gated: contagens por intervalo do ciclo</h3>
      <div class="grafico">${graficoBarras(pct)}</div>
      <p class="nota">Cada barra é a soma de todas as projeções de um intervalo, em % da média dos intervalos. Queda nos últimos intervalos sugere arritmia ou rejeição de batimentos inadequada. A janela de aceitação do intervalo R-R costuma ficar em torno de 20% (SBC 2020).</p>
      <h3 class="subtitulo">Cabeçalho do gated</h3>
      ${campos.length ? `<dl class="dados-gated">${campos.map(([k, t]) => `<div><dt>${esc(t)}</dt><dd>${esc(k === 'percentual_rejeitado' ? num(g[k], 1) : g[k])}</dd></div>`).join('')}</dl>` : ''}
      ${g.observacao ? `<p class="nota">${esc(g.observacao)}</p>` : ''}`;
  }

  function graficoLinha(xs, ys, rotX, rotY, marcado = null) {
    const W = 640;
    const H = 180;
    const m = { e: 64, d: 12, t: 12, b: 34 };
    const xmin = Math.min(...xs); const xmax = Math.max(...xs);
    const ymax = Math.max(...ys) * 1.05 || 1;
    const X = (x) => m.e + ((x - xmin) / (xmax - xmin || 1)) * (W - m.e - m.d);
    const Y = (y) => H - m.b - (y / ymax) * (H - m.t - m.b);
    const pts = xs.map((x, i) => `${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join(' ');
    const ticks = [0, 0.5, 1].map((f) => ymax * f);
    const xt = [xmin, (xmin + xmax) / 2, xmax];
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(rotY)} por ${esc(rotX)}">
      ${ticks.map((t) => `<line class="eixo-linha" x1="${m.e}" x2="${W - m.d}" y1="${Y(t)}" y2="${Y(t)}"/><text class="eixo-texto" x="${m.e - 6}" y="${Y(t) + 4}" text-anchor="end">${esc(Math.round(t).toLocaleString('pt-BR'))}</text>`).join('')}
      ${xt.map((t) => `<text class="eixo-texto" x="${X(t)}" y="${H - m.b + 16}" text-anchor="middle">${num(t, 0)}</text>`).join('')}
      <text class="eixo-texto" x="${(W + m.e) / 2}" y="${H - 4}" text-anchor="middle">${esc(rotX)}</text>
      <polyline class="serie" points="${pts}"/>
      ${marcado !== null ? `<circle class="ponto" cx="${X(xs[marcado])}" cy="${Y(ys[marcado])}" r="4"/>` : ''}
    </svg>`;
  }

  function graficoBarras(pct) {
    const W = 640;
    const H = 170;
    const m = { e: 44, d: 12, t: 16, b: 30 };
    const ymax = Math.max(120, ...pct);
    const bw = (W - m.e - m.d) / pct.length;
    const Y = (y) => H - m.b - (y / ymax) * (H - m.t - m.b);
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Contagens por intervalo do gated">
      ${[0, 50, 100].map((t) => `<line class="eixo-linha" x1="${m.e}" x2="${W - m.d}" y1="${Y(t)}" y2="${Y(t)}"/><text class="eixo-texto" x="${m.e - 6}" y="${Y(t) + 4}" text-anchor="end">${t}%</text>`).join('')}
      ${pct.map((p, i) => `<rect class="barra-g ${p < 85 ? 'baixa' : ''}" x="${m.e + i * bw + 4}" y="${Y(p)}" width="${bw - 8}" height="${Y(0) - Y(p)}"/>
        <text class="eixo-texto" x="${m.e + (i + 0.5) * bw}" y="${H - m.b + 16}" text-anchor="middle">${i + 1}</text>
        <text class="rotulo-barra" x="${m.e + (i + 0.5) * bw}" y="${Y(p) - 4}" text-anchor="middle">${num(p, 0)}</text>`).join('')}
    </svg>`;
  }

  // ----------------------------------------------------------- passo 3
  function renderRecon() {
    const f = estado.filtro;
    $('[data-corte]').value = String(f.corte);
    $('[data-ordem]').value = String(f.ordem);
    atualizarUnidades();
    const area = $('[data-previas-recon]');
    area.innerHTML = '';
    if (!estado.reconstruido) return;
    $('[data-status-recon]').textContent = `Reconstruído com Butterworth de ordem ${f.ordem} e corte ${num(f.corte, 2)} Nyquist.`;
    for (const e of estado.estudos) area.appendChild(colunaTransaxial(e, null));
  }

  function atualizarUnidades() {
    const corte = Number($('[data-corte]').value);
    const ordem = Number($('[data-ordem]').value);
    const r = cmd({ acao: 'curva_filtro', corte, ordem });
    const pixel = estado.filtro.pixel_mm;
    if (!r.ok) { $('[data-filtro-unidades]').textContent = r.erro; return; }
    const cpp = r.curva.corte_ciclos_pixel;
    $('[data-filtro-unidades]').textContent = `= ${num(cpp, 3)} ciclos/pixel${pixel ? ` = ${num(cpp / (pixel / 10), 2)} ciclos/cm (pixel de ${num(pixel, 2)} mm)` : ''}`;
    $('[data-grafico-filtro]').innerHTML = graficoFiltro(r.curva);
  }

  function graficoFiltro(c) {
    const W = 640;
    const H = 170;
    const m = { e: 40, d: 12, t: 12, b: 34 };
    const X = (x) => m.e + (x / 0.5) * (W - m.e - m.d);
    const Y = (y) => H - m.b - y * (H - m.t - m.b);
    const linha = (ys) => c.f.map((x, i) => `${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join(' ');
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Curvas do filtro">
      ${[0, 0.5, 1].map((t) => `<line class="eixo-linha" x1="${m.e}" x2="${W - m.d}" y1="${Y(t)}" y2="${Y(t)}"/><text class="eixo-texto" x="${m.e - 6}" y="${Y(t) + 4}" text-anchor="end">${num(t, 1)}</text>`).join('')}
      ${[0, 0.25, 0.5].map((t) => `<text class="eixo-texto" x="${X(t)}" y="${H - m.b + 16}" text-anchor="middle">${num(t, 2)}</text>`).join('')}
      <text class="eixo-texto" x="${(W + m.e) / 2}" y="${H - 4}" text-anchor="middle">Frequência (ciclos/pixel; Nyquist = 0,5)</text>
      <line class="guia-filtro" x1="${X(c.corte_ciclos_pixel)}" x2="${X(c.corte_ciclos_pixel)}" y1="${m.t}" y2="${H - m.b}"/>
      <polyline class="serie" points="${linha(c.butterworth)}"/>
      <polyline class="serie serie-2" points="${linha(c.rampa_butterworth)}"/>
      <text class="rotulo-serie" x="${X(0.02)}" y="${Y(1) + 14}">Butterworth</text>
      <text class="rotulo-serie rotulo-serie-2" x="${X(c.corte_ciclos_pixel) + 6}" y="${Y(0.92)}">rampa × Butterworth</text>
    </svg>`;
  }

  function corteAtual(e) {
    if (cortePorEstudo[e.estudo] === undefined) cortePorEstudo[e.estudo] = e.eixo ? e.eixo.corte_transaxial : (e.corte_sugerido ?? Math.floor(e.n_cortes / 2));
    return cortePorEstudo[e.estudo];
  }

  function colunaTransaxial(e) {
    const col = document.createElement('div');
    col.className = 'coluna-visor';
    col.innerHTML = `<p class="visor-rotulo">${esc(e.rotulo)}${e.de_gated ? ' · soma do gated' : ''} · <span data-ct="${e.estudo}"></span></p>`;
    const v = new Visor({
      chave: `trans:${e.estudo}`, largura: e.n, altura: e.n, padrao: e.janela, rotulo: `Transaxial do ${e.rotulo}`,
      pedido: () => ({ fonte: 'transaxial', estudo: e.estudo, corte: corteAtual(e) }),
    });
    col.appendChild(v.el);
    col.insertAdjacentHTML('beforeend', `<div class="controle-cine"><label class="campo">Corte <input type="range" min="0" max="${e.n_cortes - 1}" value="${corteAtual(e)}" data-corte-previa="${e.estudo}"></label></div>`);
    v.desenhar();
    $(`[data-ct="${e.estudo}"]`, col).textContent = `corte ${corteAtual(e) + 1} de ${e.n_cortes}`;
    return col;
  }

  // ----------------------------------------------------------- passo 4
  let rascunho1 = null; // {base, apice} no transaxial enquanto arrasta
  let rascunho2 = null; // {base, apice} no plano vertical enquanto arrasta
  let pegando = null;

  function renderEixos() {
    const estudos = estado.estudos;
    if (!estudos.find((e) => e.estudo === estudoEixo)) estudoEixo = estudos[0]?.estudo;
    $('[data-abas-eixo]').innerHTML = estudos.map((e) => `<button type="button" role="tab" data-aba-eixo="${e.estudo}" aria-selected="${e.estudo === estudoEixo}">${esc(e.rotulo)} ${e.eixo ? '✓' : '·'}</button>`).join('');
    const e = estudoPorNome(estudoEixo);
    if (!e) return;
    const k = corteAtual(e);
    const fatiaSlider = $('[data-corte-trans]');
    fatiaSlider.max = String(e.n_cortes - 1);
    fatiaSlider.value = String(k);
    $('[data-corte-texto]').textContent = `· corte ${k + 1} de ${e.n_cortes}`;
    rascunho1 = null; rascunho2 = null; pegando = null;

    const linha1 = () => rascunho1 || (e.eixo && e.eixo.corte_transaxial === corteAtual(e) ? { base: e.eixo.base_1, apice: e.eixo.apice_1 } : null);
    const linha2 = () => rascunho2 || (e.eixo ? { base: e.eixo.base_2, apice: e.eixo.apice_2 } : null);
    const desenharLinha = (l) => (l ? `
      <line class="eixo-sombra" x1="${l.base[0]}" y1="${l.base[1]}" x2="${l.apice[0]}" y2="${l.apice[1]}"/>
      <line class="eixo-linha-ve" x1="${l.base[0]}" y1="${l.base[1]}" x2="${l.apice[0]}" y2="${l.apice[1]}"/>
      <circle class="ponta ponta-base" cx="${l.base[0]}" cy="${l.base[1]}" r="1.3"/>
      <circle class="ponta ponta-apice" cx="${l.apice[0]}" cy="${l.apice[1]}" r="1.3"/>
      <text class="ponta-texto" x="${l.base[0]}" y="${l.base[1] - 2.2}" text-anchor="middle">B</text>
      <text class="ponta-texto" x="${l.apice[0]}" y="${l.apice[1] - 2.2}" text-anchor="middle">A</text>` : '');
    const perto = (l, p) => {
      if (!l) return null;
      const d = (q) => Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d(l.apice) < 2.5) return 'apice';
      if (d(l.base) < 2.5) return 'base';
      // no corpo da linha: arrasta a linha inteira (mesma inclinação e comprimento)
      const vx = l.apice[0] - l.base[0], vy = l.apice[1] - l.base[1];
      const t = Math.max(0, Math.min(1, ((p[0] - l.base[0]) * vx + (p[1] - l.base[1]) * vy) / (vx * vx + vy * vy || 1)));
      if (d([l.base[0] + t * vx, l.base[1] + t * vy]) < 2) return 'linha';
      return null;
    };
    let origem = null; // {p, l}: onde começou o arraste da linha inteira
    const mover = (rasc, p) => {
      if (pegando === 'linha') {
        const dx = p[0] - origem.p[0], dy = p[1] - origem.p[1];
        rasc.base = [origem.l.base[0] + dx, origem.l.base[1] + dy];
        rasc.apice = [origem.l.apice[0] + dx, origem.l.apice[1] + dy];
      } else rasc[pegando] = p;
    };

    const trans = new Visor({
      chave: `trans:${e.estudo}`, largura: e.n, altura: e.n, padrao: e.janela, rotulo: 'Transaxial',
      pedido: () => ({ fonte: 'transaxial', estudo: e.estudo, corte: corteAtual(e) }),
      sobre: () => desenharLinha(linha1()),
      aoApertar: (p) => {
        const l = linha1();
        const qual = perto(l, p);
        pegando = qual || 'apice';
        origem = { p, l };
        rascunho1 = qual ? { base: [...l.base], apice: [...l.apice] } : { base: p, apice: p };
        trans.sobrepor();
      },
      aoMover: (p) => {
        if (!rascunho1) return;
        mover(rascunho1, p);
        trans.sobrepor();
        planoAoVivo();
      },
      aoSoltar: () => {
        const l = rascunho1;
        rascunho1 = null;
        if (!l || Math.hypot(l.apice[0] - l.base[0], l.apice[1] - l.base[1]) < 2) { trans.sobrepor(); return; }
        // Linha inteira deslocada: a 2ª etapa é relativa ao meio da linha, então o eixo 3D só translada.
        const segunda = pegando === 'linha' && e.eixo ? { base_2: e.eixo.base_2, apice_2: e.eixo.apice_2 } : {};
        const r = cmd({ acao: 'definir_eixo', estudo: e.estudo, corte: corteAtual(e), base_1: l.base, apice_1: l.apice, ...segunda });
        if (!r.ok) avisar(r.erro);
        render();
      },
    });
    const plano = new Visor({
      chave: `trans:${e.estudo}`, largura: e.n, altura: e.n, padrao: e.janela, rotulo: 'Plano vertical',
      pedido: () => (rascunho1 && Math.hypot(rascunho1.apice[0] - rascunho1.base[0], rascunho1.apice[1] - rascunho1.base[1]) >= 2
        ? { fonte: 'plano_vertical', estudo: e.estudo, corte: corteAtual(e), base_1: rascunho1.base, apice_1: rascunho1.apice }
        : { fonte: 'plano_vertical', estudo: e.estudo }),
      sobre: () => (rascunho1 && pegando !== 'linha' ? '' : desenharLinha(linha2())),
      aoApertar: (p) => {
        if (!e.eixo) return;
        const l = linha2();
        const qual = perto(l, p);
        pegando = qual || 'apice';
        origem = { p, l };
        rascunho2 = qual ? { base: [...l.base], apice: [...l.apice] } : { base: p, apice: p };
        plano.sobrepor();
      },
      aoMover: (p) => { if (rascunho2) { mover(rascunho2, p); plano.sobrepor(); } },
      aoSoltar: () => {
        const l = rascunho2;
        rascunho2 = null;
        if (!l || !e.eixo || Math.hypot(l.apice[0] - l.base[0], l.apice[1] - l.base[1]) < 2) { plano.sobrepor(); return; }
        const r = cmd({ acao: 'definir_eixo', estudo: e.estudo, corte: e.eixo.corte_transaxial, base_1: e.eixo.base_1, apice_1: e.eixo.apice_1, base_2: l.base, apice_2: l.apice });
        if (!r.ok) avisar(r.erro);
        render();
      },
    });
    const planoAoVivo = () => {
      if (plano.el.isConnected && rascunho1 && Math.hypot(rascunho1.apice[0] - rascunho1.base[0], rascunho1.apice[1] - rascunho1.base[1]) >= 2) plano.desenhar();
    };
    $('[data-visor-trans]').innerHTML = '';
    $('[data-visor-trans]').appendChild(trans.el);
    trans.desenhar();
    $('[data-visor-plano]').innerHTML = '';
    if (e.eixo) {
      $('[data-visor-plano]').appendChild(plano.el);
      plano.desenhar();
    } else {
      $('[data-visor-plano]').innerHTML = '<div class="visor visor-vazio"><p>Trace primeiro a linha no transaxial.</p></div>';
    }
    const acoes = [];
    // Par natural: repouso ← estresse (e prona repouso ← prona estresse). Copiar mantém a mesma linha,
    // em mm do paciente, e o eixo curto dos dois fica com o mesmo número de cortes.
    const parDe = { repouso: 'estresse', prona_repouso: 'prona_estresse' }[e.estudo];
    const par = parDe && estudoPorNome(parDe);
    if (par?.eixo) {
      acoes.push(`<button type="button" class="mnp-btn ${e.eixo ? 'mnp-btn--pequeno' : 'mnp-btn--principal'}" data-copiar-eixo="${par.estudo}">${e.eixo ? 'Copiar de novo' : 'Copiar'} a linha do ${esc(par.rotulo.toLowerCase())}</button>`);
    }
    const outros = estado.estudos.filter((x) => x.estudo !== e.estudo && x.eixo && x.estudo !== parDe);
    for (const o of outros) acoes.push(`<button type="button" class="mnp-btn mnp-btn--pequeno" data-copiar-eixo="${o.estudo}">Copiar o eixo do ${esc(o.rotulo.toLowerCase())} e ajustar</button>`);
    if (e.eixo) acoes.push(`<button type="button" class="mnp-btn mnp-btn--pequeno" data-acao="apagar-eixo">Apagar o eixo</button>`);
    if (estado.arquivos.some((a) => a.nome.startsWith('fantoma_'))) acoes.push('<button type="button" class="mnp-btn mnp-btn--pequeno" data-acao="eixo-fantoma">Usar o eixo verdadeiro do fantoma (todos os estudos)</button>');
    $('[data-acoes-eixo]').innerHTML = acoes.join('');
    const previa = $('[data-previa-eixo]');
    previa.innerHTML = '';
    if (e.eixo) {
      const info = cmd({ acao: 'cortes' }).cortes[e.estudo];
      const lado = info.tipos.SA.lado;
      previa.appendChild(imagemColorida({ fonte: 'previa', estudo: e.estudo }, 3 * lado + 12, lado, 'previa-img'));
      previa.insertAdjacentHTML('beforeend', `<p class="nota">Eixo curto (meio do VE) · eixo longo vertical · eixo longo horizontal. Comprimento do eixo: ${num(info.comprimento_mm, 0)} mm · ${info.tipos.SA.n} cortes no eixo curto${par || e.estudo in { estresse: 1, prona_estresse: 1 } ? ' (o par estresse–repouso usa o comprimento do maior eixo, para ter o mesmo número de cortes)' : ''}.</p>`);
    } else {
      previa.innerHTML = '<p class="nota">A prévia aparece depois que o eixo for traçado.</p>';
    }
    blocoAvisos('[data-avisos-3]');
  }

  // ----------------------------------------------------------- passo 5
  function renderCortes() {
    $$('[data-mapa]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mapa === estado.mapa)));
    const info = cmd({ acao: 'cortes' }).cortes;
    $('[data-tetos]').innerHTML = estado.estudos.map((e) => `<label class="campo">Teto ${esc(e.rotulo.toLowerCase())} <input type="range" min="50" max="150" step="5" value="${info[e.estudo]?.teto ?? 100}" data-teto="${e.estudo}"> <span class="campo-nota">${info[e.estudo]?.teto ?? 100}%</span></label>`).join('');
    montarCortes($('[data-cortes]'), estado.estudos, info);
  }

  function montarCortes(area, estudos, info) {
    /* Faixas por tipo de corte; estresse e repouso uma embaixo da outra, com o mesmo número de cortes no eixo curto. */
    area.innerHTML = '';
    for (const [tipo, nome, ordem] of TIPOS_CORTE) {
      const bloco = document.createElement('section');
      bloco.className = 'bloco-cortes';
      bloco.innerHTML = `<h3 class="subtitulo">${esc(nome)} <span class="nota">(${esc(ordem)})</span></h3>`;
      for (const e of estudos) {
        const t = info[e.estudo]?.tipos[tipo];
        if (!t) continue;
        const linha = document.createElement('div');
        linha.className = 'faixa';
        linha.innerHTML = `<span class="faixa-rotulo">${esc(e.rotulo)}</span><div class="faixa-rolagem"></div>`;
        $('.faixa-rolagem', linha).appendChild(imagemColorida({ fonte: 'faixa', estudo: e.estudo, tipo }, t.largura, t.altura, 'faixa-img'));
        bloco.appendChild(linha);
      }
      area.appendChild(bloco);
    }
  }

  // ----------------------------------------------------------- passo 6
  function renderPasso6() {
    // Os cortes ficam acima dos mapas e só são refeitos ao entrar no passo ou trocar a escala,
    // não a cada clique de escore.
    $$('[data-mapa]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mapa === estado.mapa)));
    const info = cmd({ acao: 'cortes' }).cortes;
    montarCortes($('[data-cortes-polar]'), estado.estudos.filter((e) => ['estresse', 'repouso'].includes(e.estudo)), info);
    renderPolar();
  }

  function renderPolar() {
    $('[data-pincel]').innerHTML = [0, 1, 2, 3, 4, null].map((v) => `<button type="button" role="radio" class="chip-escore ${v === null ? 'apagar' : `e${v}`}" data-pincel-valor="${v === null ? '' : v}" aria-checked="${pincel === v}">${v === null ? 'Apagar' : v}</button>`).join('')
      + '<span class="nota pincel-legenda">0 normal · 1 discreta · 2 moderada · 3 acentuada · 4 ausente</span>';
    $$('[data-rotulos]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.rotulos === rotulosPolar)));
    const p = cmd({ acao: 'polar' }).polar;
    const area = $('[data-polares]');
    area.innerHTML = '';
    for (const nome of ['estresse', 'repouso']) {
      const d = p.estudos[nome];
      if (!d) continue;
      const fig = document.createElement('figure');
      fig.className = 'polar';
      fig.innerHTML = `<figcaption>${esc(estudoPorNome(nome).rotulo)}</figcaption><div class="polar-visor"></div>
        <div class="linha-acoes"><button type="button" class="mnp-btn mnp-btn--pequeno" data-todos="${nome}">Todos normais (0)</button>
        ${nome === 'repouso' && p.estudos.estresse ? '<button type="button" class="mnp-btn mnp-btn--pequeno" data-copiar-escores="estresse:repouso">Copiar do estresse</button>' : ''}</div>`;
      const visor = $('.polar-visor', fig);
      visor.appendChild(imagemColorida({ fonte: 'polar', estudo: nome }, p.lado, p.lado, 'polar-img'));
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${p.lado} ${p.lado}`);
      svg.innerHTML = d.segmentos.map((g) => {
        const s = String(g.segmento);
        const escore = d.escores[s];
        const texto = rotulosPolar === 'escores' ? (escore === null || escore === undefined ? '–' : escore) : num(d.valores[s], 0);
        return `<g class="seg" data-segmento="${s}" data-estudo="${nome}" tabindex="0" role="button" aria-label="${esc(p.nomes[s])}: escore ${escore ?? 'não pontuado'}, captação ${num(d.valores[s], 0)}%">
          <path d="${g.caminho}"/><text x="${g.rotulo[0]}" y="${g.rotulo[1] + 5}" text-anchor="middle">${esc(texto)}</text><title>${s}. ${esc(p.nomes[s])} (${esc(p.territorio[s])}) · captação ${num(d.valores[s], 0)}%</title></g>`;
      }).join('');
      visor.appendChild(svg);
      area.appendChild(fig);
    }
    renderResumo(p);
  }

  function renderResumo(p) {
    const r = cmd({ acao: 'resultados' });
    resultados = r.ok ? r : null;
    if (!r.ok) { $('[data-resumo]').innerHTML = `<p class="erro">${esc(r.erro)}</p>`; return; }
    $('[data-resumo]').innerHTML = `
      <div class="cartoes-escore">${r.resumo.map((l) => `<div class="cartao-escore"><span class="rotulo">${esc(l.titulo)}</span><span class="valor">${esc(l.texto)}</span><span class="nota">${esc(l.percentual)} do VE${l.faixa ? ` · ${esc(l.faixa)}` : ''}</span></div>`).join('')}</div>
      <div class="tabela-rolagem tabela-pequena"><table class="resultados"><thead><tr><th scope="col">Território</th><th scope="col">Segmentos</th><th scope="col">Estresse</th><th scope="col">Repouso</th><th scope="col">Diferença</th></tr></thead>
      <tbody>${r.territorios.map((t) => `<tr><th scope="row">${esc(t.nome)} (${esc(t.territorio)})</th><td>${esc(t.segmentos)}</td><td>${esc(t.estresse)}</td><td>${esc(t.repouso)}</td><td>${esc(t.diferenca)}</td></tr>`).join('')}</tbody></table></div>`;
    const opcoes = (v) => ['', 0, 1, 2, 3, 4].map((x) => `<option value="${x}" ${String(v ?? '') === String(x) ? 'selected' : ''}>${x === '' ? '–' : x}</option>`).join('');
    const tem = (n) => Boolean(p.estudos[n]);
    $('[data-tabela-segmentos]').innerHTML = `
      <thead><tr><th scope="col">Segmento</th><th scope="col">Território</th><th scope="col">Escore estresse</th><th scope="col">Escore repouso</th><th scope="col">Captação estresse</th><th scope="col">Captação repouso</th></tr></thead>
      <tbody>${r.segmentos.map((l) => `<tr>
        <th scope="row">${l.segmento}. ${esc(l.nome)}</th><td>${esc(l.territorio)}</td>
        <td>${tem('estresse') ? `<select data-escore="estresse:${l.segmento}" aria-label="Escore de estresse do segmento ${l.segmento}">${opcoes(l.estresse)}</select>` : '—'}</td>
        <td>${tem('repouso') ? `<select data-escore="repouso:${l.segmento}" aria-label="Escore de repouso do segmento ${l.segmento}">${opcoes(l.repouso)}</select>` : '—'}</td>
        <td>${esc(l.textos.captacao_estresse)}</td><td>${esc(l.textos.captacao_repouso)}</td></tr>`).join('')}</tbody>`;
    const avisos = r.avisos || [];
    $('[data-avisos-5]').innerHTML = avisos.length ? `<div class="alerta" role="status"><ul>${avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : '';
  }

  function pontuar(estudo, segmento, valor) {
    const r = cmd({ acao: 'pontuar', estudo, segmento: Number(segmento), escore: valor === '' || valor === null ? null : Number(valor) });
    if (!r.ok) avisar(r.erro);
    renderPolar();
  }

  // ----------------------------------------------------------- passo 7
  function renderLaudo() {
    const r = cmd({ acao: 'resultados' });
    resultados = r.ok ? r : null;
    $('[data-tabelas-laudo]').innerHTML = resultados ? resultados.tabelas_html : `<p class="erro">${esc(r.erro)}</p>`;
    $('[data-laudo]').innerHTML = '<p class="nota">Montando o laudo…</p>';
    depoisDePintar(atualizarLaudo);
  }

  function atualizarLaudo() {
    const r = cmd({ acao: 'laudo', paciente: $('[data-paciente]').value, data_exame: $('[data-data-exame]').value, versoes_extra: { pyodide: PYODIDE_VERSAO } });
    $('[data-laudo]').innerHTML = r.ok ? r.html : `<p class="erro">${esc(r.erro)}</p>`;
    return r;
  }

  function status(texto) { $('[data-status-copia]').textContent = texto; }

  async function copiar(tipo) {
    if (!resultados) return;
    try {
      const html = tipo === 'tabela' ? resultados.tabelas_html : atualizarLaudo().html;
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([resultados.tabelas_texto], { type: 'text/plain' }),
      })]);
      status(tipo === 'tabela' ? 'Tabelas copiadas.' : 'Laudo copiado. Se o Word não colar as imagens, use "Imprimir ou salvar PDF".');
    } catch (erro) {
      console.error(erro);
      status('O navegador não permitiu copiar. Use "Baixar Excel" ou imprima o laudo em PDF.');
    }
  }

  function baixarBlob(blob, nome) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const dataHoje = () => new Date().toISOString().slice(0, 10);

  function baixar(formato) {
    const nomes = { csv: ['csv', 'text/csv'], xlsx: ['xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'], protocolo: ['json', 'application/json'] };
    try {
      const dados = chamarBytes('exportar', { formato });
      const [ext, tipo] = nomes[formato];
      baixarBlob(new Blob([dados], { type: tipo }), `perfusao_${formato === 'protocolo' ? 'protocolo_' : ''}${dataHoje()}.${ext}`);
    } catch (erro) {
      status(mensagemPython(erro));
    }
  }

  function imprimir() {
    const r = atualizarLaudo();
    if (!r.ok) return;
    $('#area-impressao').innerHTML = `
      <div class="impressao-topo"><img src="/assets/logos/mnp-horizontal.svg" alt="MedNuclear Pragmática" height="30"></div>
      <div class="mnp-termica" aria-hidden="true"></div>${r.html}`;
    window.print();
  }

  // ------------------------------------------------------------- eventos
  function ligar() {
    document.addEventListener('click', (e) => {
      const b = e.target.closest('button, [data-acao], g.seg');
      if (!b) { if (!e.target.closest('.menu-contexto')) fecharMenu(); return; }
      const d = b.dataset;
      if (b.matches('g.seg')) { pontuar(d.estudo, d.segmento, pincel); return; }
      if (d.passo !== undefined) irPara(Number(d.passo));
      else if (d.ir !== undefined) irPara(Number(d.ir));
      else if (d.acao === 'recarregar') location.reload();
      else if (d.acao === 'fantoma') {
        $('.zona-titulo').textContent = 'Gerando o fantoma…';
        depoisDePintar(() => {
          cmd({ acao: 'carregar_fantoma' });
          $('.zona-titulo').textContent = 'Arraste os arquivos DICOM para cá ou clique para escolher';
          exibicao.clear(); qcArquivo = null; Object.keys(cortePorEstudo).forEach((k) => delete cortePorEstudo[k]);
          render();
        });
      } else if (d.acao === 'limpar') { cmd({ acao: 'limpar' }); exibicao.clear(); qcArquivo = null; Object.keys(cortePorEstudo).forEach((k) => delete cortePorEstudo[k]); irPara(0); }
      else if (d.acao === 'fechar-erros') { cmd({ acao: 'limpar_erros' }); render(); }
      else if (d.acao === 'imprimir') imprimir();
      else if (d.acao === 'cine') {
        if (cineTimer) { pararCine(); return; }
        b.setAttribute('aria-pressed', 'true');
        b.textContent = 'Pausar';
        cineTimer = setInterval(() => moverAngulo(qcAngulo + 1), 110);
      } else if (d.acao === 'filtro-padrao') {
        $('[data-corte]').value = String(estado.filtro.padrao.corte);
        $('[data-ordem]').value = String(estado.filtro.padrao.ordem);
        atualizarUnidades();
      } else if (d.acao === 'apagar-eixo') { cmd({ acao: 'apagar_eixo', estudo: estudoEixo }); render(); }
      else if (d.acao === 'eixo-fantoma') {
        const r = cmd({ acao: 'eixo_fantoma' });
        Object.keys(cortePorEstudo).forEach((k) => delete cortePorEstudo[k]);
        if (!r.ok) avisar(r.erro);
        render();
      } else if (d.remover) { cmd({ acao: 'remover_arquivo', arquivo: d.remover }); render(); }
      else if (d.abaQc) { pararCine(); qcArquivo = d.abaQc; qcDados = null; qcLinha = null; qcIntervalo = null; render(); }
      else if (d.abaEixo) { estudoEixo = d.abaEixo; render(); }
      else if (d.copiarEixo) {
        const r = cmd({ acao: 'copiar_eixo', de: d.copiarEixo, para: estudoEixo });
        delete cortePorEstudo[estudoEixo];
        if (!r.ok) avisar(r.erro);
        render();
      } else if (d.mapa) { cmd({ acao: 'definir_mapa', mapa: d.mapa }); render(); }
      else if (d.pincelValor !== undefined) { pincel = d.pincelValor === '' ? null : Number(d.pincelValor); renderPolar(); }
      else if (d.rotulos) { rotulosPolar = d.rotulos; renderPolar(); }
      else if (d.todos) { cmd({ acao: 'pontuar_todos', estudo: d.todos, escore: 0 }); renderPolar(); }
      else if (d.copiarEscores) { const [de, para] = d.copiarEscores.split(':'); cmd({ acao: 'copiar_escores', de, para }); renderPolar(); }
      else if (d.exportar) baixar(d.exportar);
      else if (d.copiar) copiar(d.copiar);
      else if (d.cinza && visorDoMenu) {
        const v = visorDoMenu;
        if (d.cinza === 'resetar') exibicao.set(v.chave, { ...(v.padrao || {}), invertido: v.janela().invertido });
        else v.janela().invertido = d.cinza === 'invertida';
        redesenhar(v.chave);
        fecharMenu();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') fecharMenu();
      const g = e.target.closest?.('g.seg');
      if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pontuar(g.dataset.estudo, g.dataset.segmento, pincel); }
      if (g && /^[0-4]$/.test(e.key)) { e.preventDefault(); pontuar(g.dataset.estudo, g.dataset.segmento, Number(e.key)); }
    });
    window.addEventListener('scroll', fecharMenu, { passive: true });

    document.addEventListener('input', (e) => {
      const t = e.target;
      if (t.matches('[data-angulo]')) { pararCine(); moverAngulo(Number(t.value)); }
      else if (t.matches('[data-linha]')) { qcLinha = Number(t.value); atualizarSino(); }
      else if (t.matches('[data-corte-trans]')) {
        cortePorEstudo[estudoEixo] = Number(t.value);
        $('[data-corte-texto]').textContent = `· corte ${Number(t.value) + 1} de ${t.max * 1 + 1}`;
        for (const v of visores.values()) if (v.chave === `trans:${estudoEixo}` && v.el.isConnected && v.el.closest('[data-visor-trans]')) v.desenhar();
      } else if (t.matches('[data-corte-previa]')) {
        const est = t.dataset.cortePrevia;
        cortePorEstudo[est] = Number(t.value);
        for (const v of visores.values()) if (v.chave === `trans:${est}`) v.desenhar();
        const rot = $(`[data-ct="${est}"]`);
        if (rot) rot.textContent = `corte ${Number(t.value) + 1} de ${Number(t.max) + 1}`;
      } else if (t.matches('[data-corte], [data-ordem]')) atualizarUnidades();
    });

    document.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.tipo !== undefined) {
        const r = cmd({ acao: 'definir_tipo', arquivo: t.dataset.tipo, tipo: t.value });
        render();
        if (!r.ok) avisar(r.erro);
      } else if (t.matches('[data-intervalo]')) {
        qcIntervalo = t.value === '' ? null : Number(t.value);
        for (const v of visores.values()) if (v.chave.startsWith('cine:')) v.desenhar();
        atualizarRotuloCine(arquivoPorId(qcArquivo));
      } else if (t.matches('[data-teto]')) {
        cmd({ acao: 'definir_teto', estudo: t.dataset.teto, teto: Number(t.value) });
        render();
      } else if (t.dataset.escore) {
        const [estudo, seg] = t.dataset.escore.split(':');
        pontuar(estudo, seg, t.value);
      } else if (t.matches('[data-paciente], [data-data-exame]')) atualizarLaudo();
    });

    $('[data-form-filtro]').addEventListener('submit', (e) => {
      e.preventDefault();
      const r = cmd({ acao: 'definir_filtro', corte: Number($('[data-corte]').value), ordem: Number($('[data-ordem]').value) });
      if (!r.ok) { avisar(r.erro); return; }
      $('[data-status-recon]').textContent = 'Reconstruindo…';
      depoisDePintar(() => { cmd({ acao: 'reconstruir' }); render(); });
    });

    const zona = $('.zona-envio');
    const entrada = $('[data-entrada-arquivos]');
    zona.addEventListener('click', () => entrada.click());
    zona.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); entrada.click(); } });
    entrada.addEventListener('change', async () => { await receberArquivos(entrada.files); entrada.value = ''; });
    zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('arrastando'); });
    zona.addEventListener('dragleave', () => zona.classList.remove('arrastando'));
    zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('arrastando'); receberArquivos(e.dataTransfer.files); });
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', (e) => e.preventDefault());
  }

  ligar();
  iniciar();
})();
