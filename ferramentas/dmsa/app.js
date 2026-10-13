/* Cintilografia renal com DMSA — interface.
 *
 * Este arquivo só cuida da tela: carregar o núcleo, receber arquivos,
 * capturar o mouse/toque, desenhar o que o núcleo devolve e copiar ou
 * baixar arquivos. Todo cálculo (leitura dos pixels, rescale, incidências,
 * ROIs, espelhamento, fundo, contagens, resultados, figuras, exportação e
 * laudo) acontece no núcleo em Python (pacote mnp-nucleo), rodando no
 * navegador pelo Pyodide.
 */
'use strict';

(() => {
  // Versão travada do Pyodide (Python + NumPy no navegador), servida pelo CDN.
  // Para atualizar: troque o número, teste a ferramenta e registre no README.
  const PYODIDE_VERSAO = '0.29.5';
  const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
  // Núcleo e pydicom: gerados pelo build e servidos pelo próprio site.
  const PACOTES_URL = new URL('/ferramentas/_pacotes/', location.href);
  const NOME_RIM = { D: 'rim direito', E: 'rim esquerdo' };

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  let pyodide = null;
  let sessao = null;
  let estado = null;
  let versoes = {};
  let passo = 0;
  let rimAtivo = 'D';
  let fundoManual = null; // {vista, rim} enquanto o usuário desenha o fundo à mão
  let gradeInvertida = false;
  let resultados = null;
  let urlsGrade = [];
  const exibicao = new Map(); // slot -> {nivel, largura, invertido}
  const visores = new Map(); // "post" | "ant" -> Visor do passo atual

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
      pyodide.runPython('from mnp_nucleo.dmsa.sessao import Sessao\nsessao = Sessao()');
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
    const v = estado.validacao;
    if (i === 0) return true;
    if (i === 1) return !v.arquivos;
    if (i === 2) return !v.rois;
    return !v.fundo;
  }

  function irPara(i) {
    if (!liberado(i)) return;
    passo = i;
    fundoManual = null;
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
    $('[data-validacao="0"]').textContent = estado?.slots.length ? v.arquivos || '' : '';
    $('[data-validacao="1"]').textContent = v.rois || '';
    $('[data-validacao="2"]').textContent = v.fundo || '';
    visores.clear();
    [renderImagens, renderRois, renderFundo, renderResultados, renderLaudo][passo]();
  }

  function blocoAvisos(seletor) {
    const avisos = estado.avisos || [];
    $(seletor).innerHTML = avisos.length
      ? `<div class="alerta" role="status"><strong>Confira:</strong><ul>${avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>`
      : '';
  }

  // ----------------------------------------------------------- passo 1
  const slotPorId = (id) => estado.slots.find((s) => s.id === id);

  function renderImagens() {
    const erros = estado.erros;
    $('[data-erros]').innerHTML = erros.length
      ? `<div class="alerta alerta--erro" role="alert"><strong>Alguns arquivos não foram lidos.</strong><ul>${erros.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
         <div class="linha-acoes"><button type="button" class="mnp-btn mnp-btn--pequeno" data-acao="fechar-erros">Fechar</button></div></div>`
      : '';
    blocoAvisos('[data-avisos-1]');
    const lista = $('[data-slots]');
    lista.innerHTML = '';
    for (const s of estado.slots) lista.appendChild(cartaoSlot(s));
    $('[data-acao="limpar"]').hidden = estado.slots.length === 0;
  }

  function cartaoSlot(s) {
    const div = document.createElement('article');
    const duplicada = estado.duplicadas.includes(s.incidencia);
    div.className = `slot ${s.incidencia === 'IGNORAR' ? 'slot--ignorado' : ''}`;
    const opcoes = estado.incidencias.map((o) => `<option value="${o.valor}" ${o.valor === s.incidencia ? 'selected' : ''}>${esc(o.valor === 'IGNORAR' ? o.rotulo : `${o.valor} · ${o.rotulo}`)}</option>`).join('');
    div.innerHTML = `
      <div class="miniatura"></div>
      <div>
        <div class="arquivo-nome"><span>${esc(s.rotulo)}</span><button type="button" data-remover="${esc(s.arquivo)}" aria-label="Remover o arquivo ${esc(s.nome)}" title="Remover o arquivo">×</button></div>
        <label class="campo campo-incidencia">Incidência
          <select data-incidencia="${esc(s.id)}">${opcoes}</select>
        </label>
        ${duplicada ? '<span class="selo">incidência repetida</span>' : ''}
        <div class="arquivo-dados">
          <span>Matriz <b>${esc(s.dimensoes)}</b></span>
          <span>Quadros <b>${s.n_quadros}</b></span>
          <span>Contagens <b>${esc(s.contagens)}</b></span>
          <span>Horário <b>${esc(s.horario || '—')}</b></span>
        </div>
        ${s.avisos.map((x) => `<p class="nota">${esc(x)}</p>`).join('')}
      </div>`;
    const v = new Visor({ slot: s, rotulo: `Miniatura de ${s.rotulo}` });
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
    /* Mostra uma imagem com as ROIs por cima e trata mouse/toque.
       modo: 'leitura', 'rois' (desenha e arrasta as ROIs) ou 'fundo'
       (mostra o fundo e desenha o fundo à mão). */
    constructor({ slot, vista = null, modo = 'leitura', rotulo = '' }) {
      Object.assign(this, { slot, vista, modo });
      this.chave = slot.id;
      this.el = document.createElement('div');
      this.el.className = `visor ${modo !== 'leitura' ? 'desenho' : ''}`;
      this.el.style.aspectRatio = `${slot.colunas} / ${slot.linhas}`;
      this.el.setAttribute('role', 'img');
      this.el.setAttribute('aria-label', rotulo);
      this.canvas = document.createElement('canvas');
      this.canvas.width = slot.colunas;
      this.canvas.height = slot.linhas;
      this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      this.svg.setAttribute('viewBox', `0 0 ${slot.colunas} ${slot.linhas}`);
      this.svg.setAttribute('preserveAspectRatio', 'none');
      this.el.append(this.canvas, this.svg);
      this.acao = null;
      this.quadroPendente = false;
      this.ligarEventos();
    }

    rois() { return this.vista ? (estado.rois[this.vista] || {}) : {}; }

    janela() {
      if (!exibicao.has(this.chave)) exibicao.set(this.chave, { ...this.slot.janela, invertido: false });
      return exibicao.get(this.chave);
    }

    desenhar() {
      const j = this.janela();
      const pedido = { slot: this.slot.id, nivel: j.nivel, largura: j.largura, invertido: j.invertido, fundo: this.modo === 'fundo' };
      const rgba = chamarBytes('imagem', pedido);
      const img = new ImageData(new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, rgba.byteLength), this.slot.colunas, this.slot.linhas);
      this.canvas.getContext('2d').putImageData(img, 0, 0);
      this.sobrepor();
    }

    sobrepor({ trocar = {}, rascunho = null, realce = null } = {}) {
      const partes = [];
      const pts = (p) => p.map((q) => `${q[0]},${q[1]}`).join(' ');
      const rois = { ...this.rois(), ...trocar };
      for (const rim of ['D', 'E']) {
        const p = rois[rim];
        if (!p || p.length < 3) continue;
        partes.push(`<polygon class="roi-sombra" points="${pts(p)}"/>`);
        partes.push(`<polygon class="roi roi-${rim}${realce === rim ? ' realce' : ''}${this.modo === 'fundo' ? ' sem-preenchimento' : ''}" points="${pts(p)}"/>`);
      }
      if (this.modo === 'fundo' && this.vista) {
        const regioes = estado.fundo.regioes[this.vista] || {};
        for (const rim of ['D', 'E']) {
          const p = regioes[rim]?.poligono;
          if (p) partes.push(`<polygon class="fundo-manual fundo-${rim}" points="${pts(p)}"/>`);
        }
      }
      if (rascunho && rascunho.pontos.length >= 2) {
        partes.push(`<polyline class="roi-sombra" points="${pts(rascunho.pontos)}"/>`);
        partes.push(`<polyline class="roi roi-${rascunho.rim} rascunho" points="${pts(rascunho.pontos)}"/>`);
      }
      this.svg.innerHTML = partes.join('');
    }

    ponto(e) {
      const r = this.svg.getBoundingClientRect();
      return [((e.clientX - r.left) / r.width) * this.slot.colunas, ((e.clientY - r.top) / r.height) * this.slot.linhas];
    }

    // Executa no máximo uma vez por quadro de animação (movimentos rápidos do mouse).
    agendar(fn) {
      this.pendente = fn;
      if (this.quadroPendente) return;
      this.quadroPendente = true;
      requestAnimationFrame(() => { this.quadroPendente = false; const f = this.pendente; this.pendente = null; f?.(); });
    }

    desenhandoFundo() { return this.modo === 'fundo' && fundoManual && fundoManual.vista === this.vista; }

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
        if (e.button !== 0 || this.modo === 'leitura' || !this.vista) return;
        e.preventDefault();
        const p = this.ponto(e);
        if (this.desenhandoFundo()) {
          this.acao = { tipo: 'fundo', rim: fundoManual.rim, pontos: [p] };
        } else if (this.modo === 'rois') {
          const rim = cmd({ acao: 'toca_roi', vista: this.vista, x: p[0], y: p[1] }).rim;
          if (rim) {
            this.acao = { tipo: 'arraste', rim, inicio: p, dx: 0, dy: 0 };
            el.classList.add('arrastando');
          } else if (this.vista === 'post') {
            this.acao = { tipo: 'desenho', rim: rimAtivo, pontos: [p] };
          } else {
            return;
          }
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
            const r = cmd({ acao: 'janela_arraste', nivel: a.nivel, largura: a.largura, dx, dy, faixa: this.slot.janela.faixa });
            Object.assign(this.janela(), { nivel: r.nivel, largura: r.largura });
            redesenharImagem(this.chave);
          });
        } else if (a?.tipo === 'arraste') {
          const p = this.ponto(e);
          a.dx = p[0] - a.inicio[0];
          a.dy = p[1] - a.inicio[1];
          this.agendar(() => {
            const r = cmd({ acao: 'arrastar_roi', vista: this.vista, rim: a.rim, dx: a.dx, dy: a.dy, confirmar: false });
            if (!r.ok) return;
            this.sobrepor({ trocar: { [a.rim]: r.roi }, realce: a.rim });
            if (r.roi_ant) visores.get('ant')?.sobrepor({ trocar: { [a.rim]: r.roi_ant }, realce: a.rim });
          });
        } else if (a?.tipo === 'desenho' || a?.tipo === 'fundo') {
          const p = this.ponto(e);
          const u = a.pontos[a.pontos.length - 1];
          if (Math.hypot(p[0] - u[0], p[1] - u[1]) >= 0.4) a.pontos.push(p);
          this.agendar(() => this.sobrepor({ rascunho: a }));
        } else if (e.pointerType === 'mouse' && this.modo === 'rois' && !this.acao) {
          const p = this.ponto(e);
          this.agendar(() => {
            const rim = cmd({ acao: 'toca_roi', vista: this.vista, x: p[0], y: p[1] }).rim;
            el.classList.toggle('pega', Boolean(rim));
            if (!this.acao) this.sobrepor({ realce: rim });
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
          const r = cmd({ acao: 'arrastar_roi', vista: this.vista, rim: a.rim, dx: a.dx, dy: a.dy, confirmar: a.dx !== 0 || a.dy !== 0 });
          if (!r.ok) avisar(r.erro);
          render();
        } else if (a.tipo === 'desenho') {
          if (a.pontos.length >= 3) {
            const r = cmd({ acao: 'desenhar_roi', rim: a.rim, pontos: a.pontos });
            if (!r.ok) { render(); avisar(r.erro); return; }
            const outro = a.rim === 'D' ? 'E' : 'D';
            if (!estado.rois.post[outro]) rimAtivo = outro;
          }
          render();
        } else if (a.tipo === 'fundo') {
          let erro = null;
          if (a.pontos.length >= 3) {
            const r = cmd({ acao: 'desenhar_fundo', vista: this.vista, rim: a.rim, pontos: a.pontos });
            if (r.ok) fundoManual = null; else erro = r.erro;
          }
          render();
          if (erro) avisar(erro);
        }
      };
      el.addEventListener('pointerup', terminar);
      el.addEventListener('pointercancel', terminar);
      el.addEventListener('pointerleave', () => { if (!this.acao && this.modo === 'rois') { el.classList.remove('pega'); this.sobrepor(); } });
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
  function colunaVisor(vista, modo, rotulo) {
    const id = vista === 'post' ? estado.post : estado.ant;
    const s = slotPorId(id);
    const col = document.createElement('div');
    col.className = 'coluna-visor';
    const quadro = s.n_quadros > 1 ? ` · quadro ${s.quadro + 1}` : '';
    col.innerHTML = `<p class="visor-rotulo">${esc(rotulo)}${quadro}</p>`;
    const v = new Visor({ slot: s, vista, modo, rotulo: vista === 'post' ? 'Posterior' : 'Anterior' });
    visores.set(vista, v);
    col.appendChild(v.el);
    return col;
  }

  function renderRois() {
    $$('[data-rim]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.rim === rimAtivo)));
    const r = estado.rois.post || {};
    $('[data-estado-rois]').innerHTML = ['D', 'E'].map((k) => `<span class="selo ${r[k] ? 'selo--neutro' : ''}">${NOME_RIM[k]}: ${r[k] ? 'ROI definida' : 'falta desenhar'}</span>`).join(' ');
    const area = $('[data-visores-rois]');
    area.innerHTML = '';
    area.appendChild(colunaVisor('post', 'rois', 'Posterior · desenhe aqui'));
    if (estado.ant) area.appendChild(colunaVisor('ant', 'rois', 'Anterior · ROIs espelhadas'));
    else area.insertAdjacentHTML('beforeend', '<div class="coluna-visor visor-vazio"><p>Sem anterior: a função relativa sai só pela posterior.</p></div>');
    const acoes = [];
    for (const k of ['D', 'E']) {
      if (r[k]) acoes.push(`<button type="button" class="mnp-btn mnp-btn--pequeno" data-apagar="${k}">Apagar a ROI do ${NOME_RIM[k]}</button>`);
      if (estado.deslocada[k]) acoes.push(`<button type="button" class="mnp-btn mnp-btn--pequeno" data-espelho="${k}">Espelhar de novo o ${NOME_RIM[k]} na anterior</button>`);
    }
    $('[data-acoes-rois]').innerHTML = acoes.join('');
    blocoAvisos('[data-avisos-2]');
    for (const v of visores.values()) v.desenhar();
  }

  function controlesFundo(vista) {
    const regioes = estado.fundo.regioes[vista] || {};
    const anel = estado.fundo.metodo === 'anel';
    const linhas = ['D', 'E'].map((k) => {
      const reg = regioes[k];
      if (!reg) return '';
      const desenhando = fundoManual && fundoManual.vista === vista && fundoManual.rim === k;
      const texto = reg.origem === 'manual' ? `à mão · ${reg.pixels} pixels` : `anel · ${reg.pixels} pixels`;
      return `<div class="linha-fundo">
        <span class="chave chave-${k}">${NOME_RIM[k]}</span>
        <span class="selo ${reg.origem === 'manual' ? '' : 'selo--neutro'}">${anel ? texto : 'sem correção'}</span>
        ${anel ? `<button type="button" class="mnp-btn mnp-btn--pequeno ${desenhando ? 'ativo' : ''}" data-fundo-desenhar="${vista}:${k}" aria-pressed="${desenhando}">${desenhando ? 'Desenhe na imagem acima' : 'Desenhar à mão'}</button>` : ''}
        ${anel && reg.origem === 'manual' ? `<button type="button" class="mnp-btn mnp-btn--pequeno" data-fundo-auto="${vista}:${k}">Voltar ao anel</button>` : ''}
      </div>`;
    }).join('');
    return `<div class="controles-fundo">${linhas}</div>`;
  }

  function renderFundo() {
    $$('[data-metodo-fundo]').forEach((r) => { r.checked = r.value === estado.fundo.metodo; });
    const area = $('[data-visores-fundo]');
    area.innerHTML = '';
    for (const vista of ['post', 'ant']) {
      if (vista === 'ant' && !estado.ant) continue;
      const col = colunaVisor(vista, 'fundo', vista === 'post' ? 'Posterior · fundo' : 'Anterior · fundo');
      if (fundoManual && fundoManual.vista === vista) col.classList.add('desenhando');
      col.insertAdjacentHTML('beforeend', controlesFundo(vista));
      area.appendChild(col);
    }
    const temManual = Object.values(estado.fundo.regioes).some((v) => Object.values(v).some((r) => r.origem === 'manual'));
    $('[data-acao="fundos-automaticos"]').hidden = !temManual;
    blocoAvisos('[data-avisos-3]');
    for (const v of visores.values()) v.desenhar();
  }

  // ----------------------------------------------------------- passo 4
  function renderResultados() {
    const r = cmd({ acao: 'resultados' });
    const erro = $('[data-erro-resultados]');
    erro.hidden = r.ok;
    erro.textContent = r.ok ? '' : r.erro;
    resultados = r.ok ? r : null;
    if (!r.ok) {
      $('[data-tabela-funcao]').innerHTML = '';
      $('[data-tabela-contagens]').innerHTML = '';
      return;
    }
    $('[data-fundo-texto]').textContent = `Fundo: ${r.fundo_texto}`;
    $('[data-tabela-funcao]').innerHTML = `
      <caption class="visually-hidden">Função relativa de cada rim. Núcleo mnp-nucleo ${esc(r.versao)}.</caption>
      <thead><tr><th scope="col">Parâmetro</th><th scope="col">Rim direito (%)</th><th scope="col">Rim esquerdo (%)</th><th scope="col">Faixa 45–55%</th></tr></thead>
      <tbody>${r.funcao.map((l) => `<tr class="${l.referencia ? 'principal' : ''}">
        <th scope="row" title="${esc(l.ajuda)}">${esc(l.titulo)}</th>
        <td class="${l.referencia ? 'destaque' : ''}">${esc(l.texto_d)}</td>
        <td class="${l.referencia ? 'destaque' : ''}">${esc(l.texto_e)}</td>
        <td>${l.referencia ? `<span class="selo ${l.referencia.dentro ? 'selo--neutro' : ''}">${l.referencia.dentro ? 'dentro' : 'fora'}</span>` : (l.d === null ? '<span class="nota">sem anterior</span>' : '<span class="nota">sem faixa</span>')}</td>
      </tr>`).join('')}</tbody>`;
    const c = r.contagens;
    $('[data-tabela-contagens]').innerHTML = `
      <thead><tr>${c.colunas.map((x) => `<th scope="col" title="${esc(x.ajuda)}">${esc(x.titulo)}</th>`).join('')}</tr></thead>
      <tbody>${c.linhas.map((l) => `<tr class="${l.vista === 'mg' ? 'linha-mg' : ''}">${c.colunas.map((x, i) => (i === 0
        ? `<th scope="row"><span class="chave chave-${l.rim}"></span>${esc(l.textos[x.chave])}</th>`
        : `<td class="${x.chave === 'corrigida' ? 'destaque' : ''}">${esc(l.textos[x.chave])}</td>`)).join('')}</tr>`).join('')}</tbody>`;
    $('[data-notas]').innerHTML = [...r.notas, `Calculado com o núcleo mnp-nucleo ${r.versao}.`].map((n) => `<li>${esc(n)}</li>`).join('');
  }

  // ----------------------------------------------------------- passo 5
  function janelas() {
    const saida = {};
    for (const [slot, j] of exibicao.entries()) saida[slot] = { nivel: j.nivel, largura: j.largura };
    return saida;
  }

  function pngDe(slot) {
    return chamarBytes('exportar', { formato: 'png', slot, invertido: gradeInvertida, janela: janelas()[slot] || null });
  }

  function renderLaudo() {
    $$('[data-cinza-grade]').forEach((b) => b.setAttribute('aria-pressed', String((b.dataset.cinzaGrade === 'invertida') === gradeInvertida)));
    const r = cmd({ acao: 'resultados' });
    resultados = r.ok ? r : null;
    const grade = $('[data-grade-laudo]');
    urlsGrade.forEach((u) => URL.revokeObjectURL(u));
    urlsGrade = [];
    grade.innerHTML = '';
    for (const q of estado.grade) {
      const url = URL.createObjectURL(new Blob([pngDe(q.slot)], { type: 'image/png' }));
      urlsGrade.push(url);
      const fig = document.createElement('figure');
      fig.className = 'quadro-laudo';
      fig.innerHTML = `<figcaption>${esc(q.rotulo)}</figcaption><img src="${url}" alt="${esc(q.rotulo)}"><button type="button" class="mnp-btn mnp-btn--pequeno" data-png="${esc(q.slot)}">Baixar PNG</button>`;
      grade.appendChild(fig);
    }
    $('[data-tabelas-laudo]').innerHTML = resultados ? resultados.tabelas_html : `<p class="erro">${esc(r.erro)}</p>`;
    atualizarLaudo();
  }

  function atualizarLaudo() {
    const r = cmd({
      acao: 'laudo',
      paciente: $('[data-paciente]').value,
      data_exame: $('[data-data-exame]').value,
      invertido: gradeInvertida,
      janelas: janelas(),
      versoes_extra: { pyodide: PYODIDE_VERSAO },
    });
    $('[data-laudo]').innerHTML = r.ok ? r.html : `<p class="erro">${esc(r.erro)}</p>`;
    return r;
  }

  // Quadros com o rótulo da incidência, compostos num canvas (só exibição).
  function carregarImagem(bytes) {
    return new Promise((ok, falha) => {
      const img = new Image();
      const url = URL.createObjectURL(new Blob([bytes], { type: 'image/png' }));
      img.onload = () => { URL.revokeObjectURL(url); ok(img); };
      img.onerror = falha;
      img.src = url;
    });
  }

  async function compor(quadros, colunas) {
    const LADO = 384;
    const FAIXA = 30;
    const GAP = 12;
    const n = quadros.length;
    const c = Math.min(colunas, n);
    const l = Math.ceil(n / c);
    const canvas = document.createElement('canvas');
    canvas.width = c * LADO + (c - 1) * GAP;
    canvas.height = l * (LADO + FAIXA) + (l - 1) * GAP;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    ctx.font = '600 15px "IBM Plex Mono", ui-monospace, monospace';
    ctx.textBaseline = 'middle';
    for (const [i, q] of quadros.entries()) {
      const x = (i % c) * (LADO + GAP);
      const y = Math.floor(i / c) * (LADO + FAIXA + GAP);
      const img = await carregarImagem(pngDe(q.slot));
      ctx.fillStyle = '#0F2740';
      ctx.fillText(q.rotulo.toUpperCase(), x + 2, y + FAIXA / 2);
      ctx.drawImage(img, x, y + FAIXA, LADO, LADO);
    }
    return new Promise((ok) => canvas.toBlob(ok, 'image/png'));
  }

  function base64DeBlob(blob) {
    return new Promise((ok) => {
      const leitor = new FileReader();
      leitor.onload = () => ok(String(leitor.result));
      leitor.readAsDataURL(blob);
    });
  }

  function status(texto) { $('[data-status-copia]').textContent = texto; }

  async function copiar(tipo) {
    if (!resultados) return;
    const itens = {};
    try {
      if (tipo === 'tabela') {
        itens['text/html'] = new Blob([resultados.tabelas_html], { type: 'text/html' });
        itens['text/plain'] = new Blob([resultados.tabelas_texto], { type: 'text/plain' });
      } else if (tipo === 'imagens') {
        itens['image/png'] = compor(estado.grade, 3);
      } else {
        const html = compor(estado.grade, 3).then(base64DeBlob).then((url) => new Blob([
          `<p><img src="${url}" alt="Imagens do estudo" width="560"></p>${resultados.tabelas_html}`,
        ], { type: 'text/html' }));
        itens['text/html'] = html;
        itens['text/plain'] = new Blob([resultados.tabelas_texto], { type: 'text/plain' });
      }
      await navigator.clipboard.write([new ClipboardItem(itens)]);
      status(tipo === 'tabela' ? 'Tabela copiada.' : tipo === 'imagens' ? 'Imagens copiadas.' : 'Imagens e tabelas copiadas.');
    } catch (erro) {
      console.error(erro);
      if (tipo === 'tabela' && copiarComSelecao(resultados.tabelas_html)) {
        status('Tabela copiada.');
      } else {
        status('O navegador não permitiu copiar. Use "Baixar PNG" e "Baixar Excel", ou imprima o laudo em PDF.');
      }
    }
  }

  // Alternativa antiga para copiar HTML (navegadores sem ClipboardItem).
  function copiarComSelecao(html) {
    const div = document.createElement('div');
    div.contentEditable = 'true';
    div.style.position = 'fixed';
    div.style.left = '-9999px';
    div.innerHTML = html;
    document.body.appendChild(div);
    const faixa = document.createRange();
    faixa.selectNodeContents(div);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(faixa);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    sel.removeAllRanges();
    div.remove();
    return ok;
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
      baixarBlob(new Blob([dados], { type: tipo }), `dmsa_${formato === 'protocolo' ? 'protocolo_' : ''}${dataHoje()}.${ext}`);
    } catch (erro) {
      const alvo = $('[data-erro-resultados]');
      alvo.hidden = false;
      alvo.textContent = mensagemPython(erro);
    }
  }

  async function baixarPng(slot) {
    const q = estado.grade.find((x) => x.slot === slot);
    const blob = await compor([q], 1);
    baixarBlob(blob, `dmsa_${q.incidencia.toLowerCase()}_${dataHoje()}.png`);
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
      else if (d.acao === 'fantoma' || d.acao === 'fantoma-mf') {
        cmd({ acao: 'carregar_fantoma', multiframe: d.acao === 'fantoma-mf' });
        exibicao.clear(); rimAtivo = 'D'; render();
      } else if (d.acao === 'limpar') { cmd({ acao: 'limpar' }); exibicao.clear(); rimAtivo = 'D'; irPara(0); }
      else if (d.acao === 'fechar-erros') { cmd({ acao: 'limpar_erros' }); render(); }
      else if (d.acao === 'imprimir') imprimir();
      else if (d.acao === 'fundos-automaticos') { cmd({ acao: 'fundo_automatico' }); fundoManual = null; render(); }
      else if (d.remover) { cmd({ acao: 'remover_arquivo', arquivo: d.remover }); render(); }
      else if (d.rim) { rimAtivo = d.rim; render(); }
      else if (d.apagar) { cmd({ acao: 'apagar_roi', rim: d.apagar }); rimAtivo = d.apagar; render(); }
      else if (d.espelho) { cmd({ acao: 'restaurar_espelho', rim: d.espelho }); render(); }
      else if (d.fundoDesenhar) {
        const [vista, rim] = d.fundoDesenhar.split(':');
        fundoManual = fundoManual && fundoManual.vista === vista && fundoManual.rim === rim ? null : { vista, rim };
        render();
      } else if (d.fundoAuto) {
        const [vista, rim] = d.fundoAuto.split(':');
        cmd({ acao: 'fundo_automatico', vista, rim }); render();
      } else if (d.exportar) baixar(d.exportar);
      else if (d.copiar) copiar(d.copiar);
      else if (d.png) baixarPng(d.png);
      else if (d.cinzaGrade) { gradeInvertida = d.cinzaGrade === 'invertida'; render(); }
      else if (d.cinza && visorDoMenu) {
        const v = visorDoMenu;
        if (d.cinza === 'resetar') exibicao.set(v.chave, { ...v.slot.janela, invertido: v.janela().invertido });
        else v.janela().invertido = d.cinza === 'invertida';
        redesenharImagem(v.chave);
        fecharMenu();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { fecharMenu(); if (fundoManual) { fundoManual = null; render(); } }
    });
    window.addEventListener('scroll', fecharMenu, { passive: true });

    document.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.incidencia !== undefined) {
        const r = cmd({ acao: 'definir_incidencia', slot: t.dataset.incidencia, incidencia: t.value });
        render();
        if (!r.ok) avisar(r.erro);
      } else if (t.matches('[data-metodo-fundo]')) {
        cmd({ acao: 'definir_fundo', metodo: t.value });
        fundoManual = null;
        render();
      } else if (t.matches('[data-paciente], [data-data-exame]')) {
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
