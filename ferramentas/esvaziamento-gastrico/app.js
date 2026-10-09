/* Esvaziamento gástrico — interface.
 *
 * Este arquivo só cuida da tela: carregar o núcleo, receber arquivos,
 * capturar o mouse/toque e desenhar o que o núcleo devolve. Todo cálculo
 * (leitura dos pixels, rescale, ROI, espelhamento, segmentação, contagens,
 * resultados, exportação e laudo) acontece no núcleo em Python
 * (pacote mnp-nucleo), rodando no navegador pelo Pyodide.
 */
'use strict';

(() => {
  // Versão travada do Pyodide (Python + NumPy no navegador), servida pelo CDN.
  // Para atualizar: troque o número, teste a ferramenta e registre no README.
  const PYODIDE_VERSAO = '0.29.5';
  const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
  // Núcleo e pydicom: gerados pelo build e servidos pelo próprio site.
  const PACOTES_URL = new URL('/ferramentas/_pacotes/', location.href);

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  let pyodide = null;
  let sessao = null;
  let estado = null;
  let versoes = {};
  let passo = 0;
  const exibicao = new Map(); // "arquivo:quadro" -> {nivel, largura, invertido}
  const visores = new Map(); // "tempo:vista" -> Visor (do passo atual)

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

  function chamarBytes(metodo, pedido) {
    return bytesDe(sessao[metodo](JSON.stringify(pedido)));
  }

  function mensagemPython(erro) {
    const texto = String(erro?.message || erro);
    const linhas = texto.trim().split('\n');
    const ultima = linhas[linhas.length - 1] || texto;
    return ultima.replace(/^[\w.]*(Error|ErroSessao|ErroDicom):\s*/, '');
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
      pyodide.runPython('from mnp_nucleo.gastrico.sessao import Sessao\nsessao = Sessao()');
      sessao = pyodide.globals.get('sessao');
      versoes = JSON.parse(pyodide.runPython('import json, mnp_nucleo\njson.dumps(mnp_nucleo.versoes())'));
      versoes.pyodide = PYODIDE_VERSAO;
      if (manifesto.nucleo && manifesto.nucleo !== versoes.mnp_nucleo) {
        throw new Error(`versão do núcleo inesperada (${versoes.mnp_nucleo}; esperada ${manifesto.nucleo})`);
      }
      etapa('iniciar', 'feita'); progresso(100);
      $('[data-versoes]').textContent =
        `Núcleo mnp-nucleo ${versoes.mnp_nucleo} · pydicom ${versoes.pydicom} · NumPy ${versoes.numpy} · Python ${versoes.python} · Pyodide ${PYODIDE_VERSAO}`;
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
    if (i === 0) return true;
    if (i === 1) return !estado.validacao.arquivos;
    return !estado.validacao.rois;
  }

  function irPara(i) {
    if (!liberado(i)) return;
    passo = i;
    $$('.passo').forEach((p) => { p.hidden = Number(p.dataset.painel) !== i; });
    render();
    $(`[data-painel="${i}"] h2`)?.focus?.({ preventScroll: true });
    if (i > 0) $('.passos').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function render() {
    $$('.passos button').forEach((b) => {
      const i = Number(b.dataset.passo);
      b.disabled = !liberado(i);
      b.classList.toggle('feito', i < passo);
      if (i === passo) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    });
    $$('[data-ir]').forEach((b) => {
      const alvo = Number(b.dataset.ir);
      if (alvo > passo) b.disabled = !liberado(alvo);
    });
    const v = estado?.validacao || {};
    $('[data-validacao="0"]').textContent = estado?.tempos.length ? v.arquivos || '' : '';
    $('[data-validacao="1"]').textContent = v.rois || '';
    $('[data-validacao="2"]').textContent = v.rois || '';
    visores.clear();
    [renderArquivos, renderRois, renderSegmentacao, renderResultados][passo]();
  }

  // ----------------------------------------------------------- passo 1
  const arquivoPorId = (id) => estado.arquivos.find((a) => a.id === id);

  function renderArquivos() {
    const erros = estado.erros;
    $('[data-erros]').innerHTML = erros.length
      ? `<div class="alerta alerta--erro" role="alert"><strong>Alguns arquivos não foram lidos.</strong><ul>${erros.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
         <div class="linha-acoes"><button type="button" class="mnp-btn mnp-btn--pequeno" data-acao="fechar-erros">Fechar</button></div></div>`
      : '';
    $('[data-sugestoes]').innerHTML = estado.sugestoes.map((s) => `
      <div class="alerta" role="status"><strong>${esc(s.nome)}</strong>: arquivo com ${s.n_quadros} quadros. Usar o quadro 1 como anterior e o quadro 2 como posterior?
        <div class="linha-acoes">
          <button type="button" class="mnp-btn mnp-btn--pequeno mnp-btn--principal" data-mf-aceitar="${esc(s.arquivo)}">Usar quadros 1 e 2 como ANT e PÓS</button>
          <button type="button" class="mnp-btn mnp-btn--pequeno" data-mf-dispensar="${esc(s.arquivo)}">Dispensar</button>
        </div></div>`).join('');

    const lista = $('[data-tempos]');
    lista.innerHTML = '';
    for (const t of estado.tempos) {
      const el = document.createElement('article');
      el.className = 'tempo';
      el.innerHTML = `
        <div class="tempo-cab">
          <span class="rotulo-t">${t.rotulo}</span>
          <label class="campo">Tempo decorrido (min)
            <input type="text" inputmode="decimal" value="${esc(t.minutos_texto)}" data-minutos="${t.indice}" aria-label="Tempo decorrido de ${t.rotulo}, em minutos">
          </label>
          ${t.horario_ausente ? '<span class="selo">horário não encontrado: preencha à mão</span>' : ''}
          ${t.dimensoes_diferentes ? '<span class="selo">ANT e PÓS com dimensões diferentes</span>' : ''}
        </div>
        <div class="pares"></div>`;
      const pares = $('.pares', el);
      pares.appendChild(cartaoArquivo(t.ant, 'anterior'));
      pares.appendChild(cartaoArquivo(t.post, 'posterior'));
      lista.appendChild(el);
    }
    $('[data-acao="limpar"]').hidden = estado.arquivos.length === 0;
  }

  function cartaoArquivo(id, esperado) {
    const div = document.createElement('div');
    if (!id) {
      div.className = 'arquivo arquivo--vazio';
      div.textContent = esperado === 'anterior' ? 'Falta a anterior' : 'Falta a posterior';
      return div;
    }
    const a = arquivoPorId(id);
    div.className = 'arquivo';
    const quadros = a.n_quadros > 1
      ? `<span class="selo selo--neutro">${a.n_quadros} quadros</span>
         <select data-quadro="${esc(a.id)}" aria-label="Quadro usado">${Array.from({ length: a.n_quadros }, (_, i) => `<option value="${i}" ${i === a.quadro ? 'selected' : ''}>Quadro ${i + 1}</option>`).join('')}</select>`
      : '';
    div.innerHTML = `
      <div class="miniatura"></div>
      <div>
        <div class="arquivo-nome"><span>${esc(a.nome)}</span><button type="button" data-remover="${esc(a.id)}" aria-label="Remover ${esc(a.nome)}" title="Remover">×</button></div>
        <div class="arquivo-ctrl">
          <span class="alternar" role="group" aria-label="Vista">
            <button type="button" data-vista="anterior" data-arquivo="${esc(a.id)}" aria-pressed="${a.vista === 'anterior'}">ANT</button>
            <button type="button" data-vista="posterior" data-arquivo="${esc(a.id)}" aria-pressed="${a.vista === 'posterior'}">PÓS</button>
          </span>
          ${quadros}
          ${a.horario_encontrado ? '' : '<span class="selo">sem horário</span>'}
        </div>
        <div class="arquivo-dados">
          <span>Horário <b>${esc(a.horario || '—')}</b></span>
          <span>Matriz <b>${esc(a.dimensoes)}</b></span>
          <span>Contagens <b>${esc(a.contagens)}</b></span>
        </div>
        ${a.avisos.map((x) => `<p class="nota">${esc(x)}</p>`).join('')}
      </div>`;
    const v = new Visor({ arquivo: a, modo: 'leitura', rotulo: `Miniatura de ${a.nome}` });
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
      const dados = new Uint8Array(await f.arrayBuffer());
      estado = JSON.parse(sessao.adicionar_arquivo(f.name, dados)).estado;
    }
    zona.textContent = original;
    render();
  }

  // ----------------------------------------------------------- visor
  class Visor {
    /* Mostra uma imagem com a ROI por cima e trata mouse/toque.
       modo: 'desenho' (desenha e arrasta), 'arraste' (só arrasta) ou 'leitura'. */
    constructor({ arquivo, tempo = null, vista = 'ant', modo = 'leitura', segmentacao = false, rotulo = '' }) {
      Object.assign(this, { arquivo, tempo, vista, modo, segmentacao });
      this.chave = `${arquivo.id}:${arquivo.quadro}`;
      this.el = document.createElement('div');
      this.el.className = `visor ${modo === 'desenho' ? 'desenho' : ''}`;
      this.el.style.aspectRatio = `${arquivo.colunas} / ${arquivo.linhas}`;
      this.el.setAttribute('role', 'img');
      this.el.setAttribute('aria-label', rotulo);
      this.canvas = document.createElement('canvas');
      this.canvas.width = arquivo.colunas;
      this.canvas.height = arquivo.linhas;
      this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      this.svg.setAttribute('viewBox', `0 0 ${arquivo.colunas} ${arquivo.linhas}`);
      this.svg.setAttribute('preserveAspectRatio', 'none');
      this.el.append(this.canvas, this.svg);
      this.acao = null;
      this.quadroPendente = false;
      this.ligarEventos();
    }

    get tempoEstado() { return this.tempo === null ? null : estado.tempos[this.tempo]; }
    get roi() {
      const t = this.tempoEstado;
      if (!t) return null;
      return this.vista === 'ant' ? t.roi : t.roi_post;
    }

    janela() {
      if (!exibicao.has(this.chave)) exibicao.set(this.chave, { ...this.arquivo.janela, invertido: false });
      return exibicao.get(this.chave);
    }

    desenhar({ semSegmentacao = false } = {}) {
      const j = this.janela();
      const pedido = { arquivo: this.arquivo.id, nivel: j.nivel, largura: j.largura, invertido: j.invertido };
      if (this.segmentacao && !semSegmentacao && this.tempoEstado?.segmentacao) {
        pedido.segmentacao = { tempo: this.tempo, vista: this.vista };
      }
      const rgba = chamarBytes('imagem', pedido);
      const img = new ImageData(new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, rgba.byteLength), this.arquivo.colunas, this.arquivo.linhas);
      this.canvas.getContext('2d').putImageData(img, 0, 0);
      this.sobrepor(this.roi, { linha: !semSegmentacao });
    }

    sobrepor(poligono, { rascunho = false, realce = false, linha = true } = {}) {
      const partes = [];
      if (poligono && poligono.length >= 2) {
        const pts = poligono.map((p) => `${p[0]},${p[1]}`).join(' ');
        const tag = rascunho ? 'polyline' : 'polygon';
        const comSeg = this.segmentacao && this.tempoEstado?.segmentacao && linha ? ' com-seg' : '';
        partes.push(`<${tag} class="roi-sombra" points="${pts}"/>`);
        partes.push(`<${tag} class="roi${rascunho ? ' rascunho' : ''}${realce ? ' realce' : ''}${comSeg}" points="${pts}"/>`);
      }
      const seg = this.tempoEstado?.segmentacao;
      if (this.segmentacao && seg && linha && !rascunho) {
        const [a, b] = this.vista === 'ant' ? seg.linha_ant : seg.linha_post;
        partes.push(`<line class="divisao-sombra" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`);
        partes.push(`<line class="divisao" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`);
      }
      this.svg.innerHTML = partes.join('');
    }

    ponto(e) {
      const r = this.svg.getBoundingClientRect();
      return [((e.clientX - r.left) / r.width) * this.arquivo.colunas, ((e.clientY - r.top) / r.height) * this.arquivo.linhas];
    }

    // Executa no máximo uma vez por quadro de animação (movimentos rápidos do mouse).
    agendar(fn) {
      this.pendente = fn;
      if (this.quadroPendente) return;
      this.quadroPendente = true;
      requestAnimationFrame(() => { this.quadroPendente = false; const f = this.pendente; this.pendente = null; f?.(); });
    }

    ligarEventos() {
      const el = this.el;
      el.addEventListener('contextmenu', (e) => { e.preventDefault(); abrirMenu(e, this); });
      el.addEventListener('auxclick', (e) => {
        if (e.button === 1 && e.detail === 2) { exibicao.delete(this.chave); redesenharImagem(this.chave); }
      });
      el.addEventListener('pointerdown', (e) => {
        if (e.button === 2) return;
        if (e.button === 1) {
          e.preventDefault();
          const j = this.janela();
          this.acao = { tipo: 'janela', x: e.clientX, y: e.clientY, nivel: j.nivel, largura: j.largura };
          el.classList.add('janela');
          el.setPointerCapture(e.pointerId);
          return;
        }
        if (e.button !== 0 || this.modo === 'leitura' || !this.tempoEstado) return;
        e.preventDefault();
        const p = this.ponto(e);
        if (this.roi && cmd({ acao: 'toca_roi', tempo: this.tempo, x: p[0], y: p[1] }).toca) {
          this.acao = { tipo: 'arraste', inicio: p, dx: 0, dy: 0 };
          el.classList.add('arrastando');
          if (this.segmentacao) { this.desenhar({ semSegmentacao: true }); this.parceiro()?.desenhar({ semSegmentacao: true }); }
        } else if (this.modo === 'desenho') {
          this.acao = { tipo: 'desenho', pontos: [p] };
        } else {
          return;
        }
        el.setPointerCapture(e.pointerId);
      });
      el.addEventListener('pointermove', (e) => {
        const a = this.acao;
        if (a?.tipo === 'janela') {
          const dx = e.clientX - a.x;
          const dy = e.clientY - a.y;
          this.agendar(() => {
            const r = cmd({ acao: 'janela_arraste', nivel: a.nivel, largura: a.largura, dx, dy, faixa: this.arquivo.janela.faixa });
            Object.assign(this.janela(), { nivel: r.nivel, largura: r.largura });
            redesenharImagem(this.chave);
          });
        } else if (a?.tipo === 'arraste') {
          const p = this.ponto(e);
          a.dx = p[0] - a.inicio[0];
          a.dy = p[1] - a.inicio[1];
          this.agendar(() => {
            const r = cmd({ acao: 'arrastar_roi', tempo: this.tempo, dx: a.dx, dy: a.dy, confirmar: false });
            if (!r.ok) return;
            this.sobrepor(r.roi, { realce: true, linha: false });
            this.parceiro()?.sobrepor(r.roi_post, { realce: true, linha: false });
          });
        } else if (a?.tipo === 'desenho') {
          const p = this.ponto(e);
          const u = a.pontos[a.pontos.length - 1];
          if (Math.hypot(p[0] - u[0], p[1] - u[1]) >= 0.5) a.pontos.push(p);
          this.agendar(() => this.sobrepor(a.pontos, { rascunho: true }));
        } else if (e.pointerType === 'mouse' && this.modo !== 'leitura' && this.roi) {
          const p = this.ponto(e);
          this.agendar(() => {
            const toca = cmd({ acao: 'toca_roi', tempo: this.tempo, x: p[0], y: p[1] }).toca;
            el.classList.toggle('pega', toca);
            if (!this.acao) this.sobrepor(this.roi, { realce: toca });
          });
        }
      });
      const terminar = () => {
        const a = this.acao;
        this.acao = null;
        this.pendente = null;
        el.classList.remove('janela', 'arrastando');
        if (!a) return;
        if (a.tipo === 'arraste') {
          const r = cmd({ acao: 'arrastar_roi', tempo: this.tempo, dx: a.dx, dy: a.dy, confirmar: a.dx !== 0 || a.dy !== 0 });
          if (!r.ok) avisar(r.erro);
          render();
        } else if (a.tipo === 'desenho') {
          if (a.pontos.length >= 3) {
            const r = cmd({ acao: 'desenhar_roi', tempo: this.tempo, pontos: a.pontos });
            if (!r.ok) avisar(r.erro);
          }
          render();
        }
      };
      el.addEventListener('pointerup', terminar);
      el.addEventListener('pointercancel', terminar);
      el.addEventListener('pointerleave', () => { if (!this.acao) { el.classList.remove('pega'); this.sobrepor(this.roi); } });
    }

    parceiro() {
      return visores.get(`${this.tempo}:${this.vista === 'ant' ? 'post' : 'ant'}`);
    }
  }

  function redesenharImagem(chave) {
    for (const v of visores.values()) if (v.chave === chave) v.desenhar();
  }

  function avisar(texto) {
    const alvo = $(`[data-validacao="${passo}"]`);
    if (alvo) alvo.textContent = texto;
  }

  // ------------------------------------------------------- menu de contexto
  let visorDoMenu = null;
  function abrirMenu(e, visor) {
    visorDoMenu = visor;
    const menu = $('.menu-contexto');
    const inv = visor.janela().invertido;
    $('[data-cinza="normal"]', menu).setAttribute('aria-checked', String(!inv));
    $('[data-cinza="invertida"]', menu).setAttribute('aria-checked', String(inv));
    menu.hidden = false;
    const { innerWidth: w, innerHeight: h } = window;
    menu.style.left = `${Math.min(e.clientX, w - menu.offsetWidth - 8)}px`;
    menu.style.top = `${Math.min(e.clientY, h - menu.offsetHeight - 8)}px`;
    $('button', menu).focus();
  }
  function fecharMenu() { $('.menu-contexto').hidden = true; visorDoMenu = null; }

  // ----------------------------------------------------------- passos 2 e 3
  function cartaoTempo(t, comSegmentacao) {
    const art = document.createElement('article');
    art.className = 'cartao-tempo';
    const temRoi = Boolean(t.roi);
    art.innerHTML = `
      <header>
        <h3>${t.rotulo} <span class="min">${esc(t.minutos_texto)} min</span></h3>
        ${comSegmentacao ? '' : `<span>
          <span class="selo ${temRoi ? '' : 'selo--neutro'}">${temRoi ? 'ROI definida' : 'sem ROI'}</span>
          <button type="button" class="mnp-btn mnp-btn--pequeno" data-copiar="${t.indice}" ${temRoi ? '' : 'disabled'}>Usar esta ROI em todos</button>
        </span>`}
      </header>`;
    if (t.bloqueio) {
      art.insertAdjacentHTML('beforeend', `<p class="erro">${esc(t.bloqueio)}</p>`);
      return art;
    }
    if (comSegmentacao && !t.segmentacao) {
      art.insertAdjacentHTML('beforeend', '<p class="erro">Sem segmentação: confira a ROI deste tempo.</p>');
      return art;
    }
    const par = document.createElement('div');
    par.className = 'par-visores';
    for (const [vista, id] of [['ant', t.ant], ['post', t.post]]) {
      const a = arquivoPorId(id);
      const quadro = a.n_quadros > 1 ? ` · quadro ${a.quadro + 1}` : '';
      const col = document.createElement('div');
      col.innerHTML = `<p class="visor-rotulo">${vista === 'ant' ? (comSegmentacao ? 'Anterior' : 'Anterior · desenhe aqui') : 'Posterior · ROI espelhada'}${quadro}</p>`;
      const modo = vista === 'ant' ? (comSegmentacao ? 'arraste' : 'desenho') : 'leitura';
      const v = new Visor({ arquivo: a, tempo: t.indice, vista, modo, segmentacao: comSegmentacao, rotulo: `${vista === 'ant' ? 'Anterior' : 'Posterior'} ${t.rotulo}` });
      visores.set(`${t.indice}:${vista}`, v);
      col.appendChild(v.el);
      par.appendChild(col);
    }
    art.appendChild(par);
    if (comSegmentacao) {
      art.insertAdjacentHTML('beforeend', `<p class="contagem-seg">Pixels na anterior: proximal ${t.segmentacao.pixels_proximal} · distal ${t.segmentacao.pixels_distal}</p>`);
    }
    return art;
  }

  function renderGrade(seletor, comSegmentacao) {
    const grade = $(seletor);
    grade.innerHTML = '';
    for (const t of estado.tempos) grade.appendChild(cartaoTempo(t, comSegmentacao));
    for (const v of visores.values()) v.desenhar();
  }
  const renderRois = () => renderGrade('[data-rois]', false);
  const renderSegmentacao = () => renderGrade('[data-segmentacao]', true);

  // ----------------------------------------------------------- passo 4
  function parametros() {
    return { decaimento: $('[data-decaimento]').checked, meia_vida: $('[data-meia-vida]').value };
  }

  function renderResultados() {
    const p = parametros();
    $('[data-meia-vida]').disabled = !p.decaimento;
    const r = cmd({ acao: 'resultados', ...p });
    const erro = $('[data-erro-resultados]');
    erro.hidden = r.ok;
    erro.textContent = r.ok ? '' : r.erro;
    if (!r.ok) {
      $('[data-tabela]').innerHTML = '';
      $('[data-curva]').innerHTML = '';
      $('[data-laudo]').innerHTML = '';
      return;
    }
    const destaque = new Set(['retencao']);
    $('[data-tabela]').innerHTML = `
      <caption class="visually-hidden">Resultados por tempo. Núcleo mnp-nucleo ${esc(r.versao)}.</caption>
      <thead><tr>${r.colunas.map((c) => `<th scope="col" title="${esc(c.ajuda)}">${esc(c.titulo)}</th>`).join('')}</tr></thead>
      <tbody>${r.linhas.map((l) => `<tr>${r.colunas.map((c, i) => (i === 0
        ? `<th scope="row">${esc(l.textos[c.chave])}</th>`
        : `<td class="${destaque.has(c.chave) ? 'destaque' : ''}">${esc(l.textos[c.chave])}</td>`)).join('')}</tr>`).join('')}</tbody>`;
    $('[data-notas]').innerHTML = [...r.notas, `Calculado com o núcleo mnp-nucleo ${r.versao}.`].map((n) => `<li>${esc(n)}</li>`).join('');
    $('[data-curva]').innerHTML = r.svg; // SVG gerado pelo núcleo, com textos escapados
    atualizarLaudo();
  }

  function atualizarLaudo() {
    const r = cmd({ acao: 'laudo', ...parametros(), identificacao: $('[data-identificacao]').value, versoes_extra: { pyodide: PYODIDE_VERSAO } });
    $('[data-laudo]').innerHTML = r.ok ? r.html : `<p class="erro">${esc(r.erro)}</p>`;
    return r;
  }

  function baixar(formato) {
    const nomes = { csv: ['csv', 'text/csv'], xlsx: ['xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'], protocolo: ['json', 'application/json'] };
    try {
      const dados = chamarBytes('exportar', { formato, ...parametros() });
      const [ext, tipo] = nomes[formato];
      const url = URL.createObjectURL(new Blob([dados], { type: tipo }));
      const a = document.createElement('a');
      const data = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `esvaziamento-gastrico_${formato === 'protocolo' ? 'protocolo_' : ''}${data}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (erro) {
      const alvo = $('[data-erro-resultados]');
      alvo.hidden = false;
      alvo.textContent = mensagemPython(erro);
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
      const b = e.target.closest('button, [data-acao]');
      if (!b) { if (!e.target.closest('.menu-contexto')) fecharMenu(); return; }
      const d = b.dataset;
      if (d.passo !== undefined) irPara(Number(d.passo));
      else if (d.ir !== undefined) irPara(Number(d.ir));
      else if (d.acao === 'recarregar') location.reload();
      else if (d.acao === 'fantoma') { cmd({ acao: 'carregar_fantoma' }); exibicao.clear(); render(); }
      else if (d.acao === 'limpar') { cmd({ acao: 'limpar' }); exibicao.clear(); irPara(0); }
      else if (d.acao === 'fechar-erros') { cmd({ acao: 'limpar_erros' }); render(); }
      else if (d.acao === 'imprimir') imprimir();
      else if (d.mfAceitar) { cmd({ acao: 'aceitar_multiframe', arquivo: d.mfAceitar }); render(); }
      else if (d.mfDispensar) { cmd({ acao: 'dispensar_sugestao', arquivo: d.mfDispensar }); render(); }
      else if (d.remover) { cmd({ acao: 'remover_arquivo', arquivo: d.remover }); render(); }
      else if (d.vista && d.arquivo) { cmd({ acao: 'definir_vista', arquivo: d.arquivo, vista: d.vista }); render(); }
      else if (d.copiar !== undefined) { cmd({ acao: 'copiar_roi', tempo: Number(d.copiar) }); render(); }
      else if (d.exportar) baixar(d.exportar);
      else if (d.cinza && visorDoMenu) {
        const v = visorDoMenu;
        if (d.cinza === 'resetar') exibicao.set(v.chave, { ...v.arquivo.janela, invertido: v.janela().invertido });
        else v.janela().invertido = d.cinza === 'invertida';
        redesenharImagem(v.chave);
        fecharMenu();
      }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharMenu(); });
    window.addEventListener('scroll', fecharMenu, { passive: true });

    document.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.minutos !== undefined) {
        const r = cmd({ acao: 'definir_minutos', tempo: Number(t.dataset.minutos), valor: t.value });
        if (!r.ok) { cmd({ acao: 'estado' }); avisar(r.erro); }
        render();
        if (!r.ok) avisar(r.erro);
      } else if (t.dataset.quadro !== undefined) {
        cmd({ acao: 'definir_quadro', arquivo: t.dataset.quadro, quadro: Number(t.value) });
        render();
      } else if (t.matches('[data-decaimento], [data-meia-vida]')) {
        renderResultados();
      } else if (t.matches('[data-identificacao]')) {
        atualizarLaudo();
      }
    });

    const zona = $('.zona-envio');
    const entrada = $('[data-entrada-arquivos]');
    zona.addEventListener('click', () => entrada.click());
    zona.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); entrada.click(); } });
    entrada.addEventListener('change', async () => { await receberArquivos(entrada.files); entrada.value = ''; });
    zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('arrastando'); });
    zona.addEventListener('dragleave', () => zona.classList.remove('arrastando'));
    zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('arrastando'); receberArquivos(e.dataTransfer.files); });
    // Evita que o navegador abra um arquivo solto fora da zona.
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', (e) => e.preventDefault());
  }

  ligar();
  iniciar();
})();
