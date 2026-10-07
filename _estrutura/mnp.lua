--[[
  MedNuclear Pragmática — filtro Lua do site.

  O que ele faz (você não precisa mexer aqui para escrever posts):
  1. Calcula o tempo de leitura de cada texto (`tempo-leitura`), se você não informar.
  2. Transforma as categorias (Oncologia, Endocrinologia, Cardiologia) em etiquetas
     com o ponto colorido do sistema de design.
  3. Monta a "Ficha do estudo" a partir de um bloco ::: {.ficha-estudo}.
  4. Monta a moldura de imagem do Caso clínico a partir de ::: {.imagem-caso}.
  5. Esconde a conclusão do caso dentro de ::: {.desfecho} até o leitor abrir.
  6. Acrescenta, no fim de cada post, o aviso educacional e o link para a série.
     (O botão da newsletter está desligado: veja NEWSLETTER_ATIVA abaixo.)
  7. Monta o formulário da newsletter (nome e e-mail) a partir de ::: {.formulario-newsletter},
     ligado ao Buttondown pelo campo `buttondown-usuario` de _quarto.yml.
]]

local stringify = pandoc.utils.stringify

local CLASSE_ESPECIALIDADE = {
  ["oncologia"] = "onco",
  ["endocrinologia"] = "endo",
  ["cardiologia"] = "cardio",
}

local function html(s) return pandoc.RawBlock("html", s) end
local function html_inline(s) return pandoc.RawInline("html", s) end

local function escapar(s)
  return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

-- caminho relativo até a raiz do site (ex.: "../..")
local function raiz()
  local ok, off = pcall(function() return quarto.project.offset() end)
  if ok and off and off ~= "" then return off end
  return "."
end

local function contar_palavras(blocks)
  local n = 0
  pandoc.walk_block(pandoc.Div(blocks), {
    Str = function(el) n = n + 1 end,
  })
  return n
end

-- ---------------------------------------------------------------- Ficha do estudo
local function ficha(div)
  local estudo = div.attributes["estudo"] or ""
  local fonte = div.attributes["fonte"] or ""
  local cab = {}
  if estudo ~= "" then table.insert(cab, escapar(estudo)) end
  if fonte ~= "" then table.insert(cab, escapar(fonte)) end

  local conteudo = {
    html('<div class="mnp-ficha__cab"><p class="mnp-ficha__titulo">Ficha do estudo</p>'
      .. (#cab > 0 and ('<span>' .. table.concat(cab, " · ") .. '</span>') or "")
      .. '</div>')
  }
  for _, b in ipairs(div.content) do
    if b.t == "Div" and b.classes:includes("pratica") then
      local inner = { html('<p class="mnp-ficha__rotulo">O que muda na prática</p>') }
      for _, x in ipairs(b.content) do table.insert(inner, x) end
      table.insert(conteudo, pandoc.Div(inner, pandoc.Attr("", { "mnp-ficha__pratica" })))
    else
      table.insert(conteudo, b)
    end
  end
  return pandoc.Div(conteudo, pandoc.Attr(div.identifier, { "mnp-ficha" }, { ["aria-label"] = "Ficha do estudo", role = "region" }))
end

-- ---------------------------------------------------------------- Imagem do caso
local function imagem_caso(div)
  local dados = div.attributes["dados"] or ""
  local conteudo = {}
  for _, b in ipairs(div.content) do table.insert(conteudo, b) end
  table.insert(conteudo, html('<div class="mnp-termica mnp-termica--vertical" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>'))
  local blocos = { pandoc.Div(conteudo, pandoc.Attr("", { "mnp-visor__quadro" })) }
  if dados ~= "" then
    table.insert(blocos, html('<p class="mnp-visor__dados">' .. escapar(dados) .. '</p>'))
  end
  return pandoc.Div(blocos, pandoc.Attr(div.identifier, { "mnp-visor" }))
end

-- ---------------------------------------------------------------- Desfecho escondido
local function desfecho(div)
  local rotulo = div.attributes["rotulo"] or "Ver a conclusão"
  local blocos = { html('<details class="mnp-desfecho"><summary>' .. escapar(rotulo) .. '</summary><div class="mnp-desfecho__corpo">') }
  for _, b in ipairs(div.content) do table.insert(blocos, b) end
  table.insert(blocos, html('</div></details>'))
  return blocos
end

-- ---------------------------------------------------------------- Formulário da newsletter
local USUARIO_BUTTONDOWN = ""

-- Botão "Receber a newsletter" no fim de cada post. Troque para true ao religar a newsletter.
local NEWSLETTER_ATIVA = false

local function formulario(div)
  local u = USUARIO_BUTTONDOWN:gsub("^%s+", ""):gsub("%s+$", "")
  local ativo = u ~= "" and u:match("^[%w%-_]+$") ~= nil
  local acao = ativo and ("https://buttondown.com/api/emails/embed-subscribe/" .. u) or "#"
  local desativado = ativo and "" or " disabled"
  local h = '<form class="mnp-form" id="formulario-newsletter" action="' .. acao .. '" method="post"'
    .. (ativo and "" or ' aria-describedby="nl-aviso"') .. '>'
    .. '<fieldset' .. desativado .. '>'
    .. '<legend class="visually-hidden">Inscrição na newsletter</legend>'
    .. '<div class="mnp-campo"><label for="nl-nome">Nome</label>'
    .. '<input id="nl-nome" name="metadata__nome" type="text" autocomplete="name" required maxlength="80"></div>'
    .. '<div class="mnp-campo"><label for="nl-email">E-mail</label>'
    .. '<input id="nl-email" name="email" type="email" autocomplete="email" inputmode="email" required></div>'
    .. '<input type="hidden" name="embed" value="1">'
    .. '<button class="mnp-btn mnp-btn--principal" type="submit">Receber a newsletter</button>'
    .. '</fieldset>'
  if ativo then
    h = h .. '<p class="mnp-form__nota">Depois de enviar, você recebe um e-mail para confirmar a inscrição. Todo e-mail da newsletter traz um link para sair.</p>'
  else
    h = h .. '<p class="mnp-form__nota mnp-form__nota--aviso" id="nl-aviso">As inscrições abrem em breve.</p>'
  end
  h = h .. '</form>'
  return html(h)
end

local function Meta(meta)
  if meta["buttondown-usuario"] ~= nil then
    USUARIO_BUTTONDOWN = stringify(meta["buttondown-usuario"])
  end
  return nil
end

local function Div(div)
  if div.classes:includes("formulario-newsletter") then return formulario(div) end
  if div.classes:includes("ficha-estudo") then return ficha(div) end
  if div.classes:includes("imagem-caso") then return imagem_caso(div) end
  if div.classes:includes("desfecho") then return desfecho(div) end
  return nil
end

-- ---------------------------------------------------------------- Documento
local function Pandoc(doc)
  local meta = doc.meta

  -- etiquetas de especialidade a partir das categorias
  if meta.categories then
    local etiquetas = pandoc.List()
    local cats = meta.categories
    if pandoc.utils.type(cats) ~= "List" then cats = { cats } end
    for _, c in ipairs(cats) do
      local nome = stringify(c)
      local classe = CLASSE_ESPECIALIDADE[nome:lower()] or "neutra"
      etiquetas:insert(pandoc.MetaMap({
        nome = pandoc.MetaString(nome),
        classe = pandoc.MetaString(classe),
        ancora = pandoc.MetaString(nome),
      }))
    end
    meta.etiquetas = pandoc.MetaList(etiquetas)
  end

  local eh_post = meta.serie ~= nil and meta["pagina-serie"] == nil

  -- tempo de leitura (cerca de 200 palavras por minuto, arredondado para cima, como nas listagens)
  if eh_post and meta["tempo-leitura"] == nil then
    local n = contar_palavras(doc.blocks)
    local min = math.max(1, math.ceil(n / 200))
    meta["tempo-leitura"] = pandoc.MetaString(min .. " min de leitura")
  end

  -- fecho de cada post
  if eh_post then
    local r = raiz()
    doc.blocks:insert(html(
      '<div class="mnp-fecho" role="complementary" aria-label="Sobre este conteúdo">'
      .. '<div class="mnp-termica" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>'
      .. '<p>Conteúdo educacional, sem relação com produtos ou serviços. Não substitui a avaliação médica de cada paciente. '
      .. '<a href="' .. r .. '/sobre.html">Política editorial</a>.</p>'
      .. '<p>' .. (NEWSLETTER_ATIVA and ('<a class="mnp-btn mnp-btn--principal" href="' .. r .. '/newsletter.html">Receber a newsletter</a> ') or '')
      .. '<a class="mnp-btn" href="' .. r .. '/' .. stringify(meta["serie-pasta"] or "") .. '/index.html">Ver todos os '
      .. escapar(stringify(meta["serie-plural"] or meta.serie):lower()) .. '</a></p>'
      .. '</div>'))
  end

  doc.meta = meta
  return doc
end

return {
  { Meta = Meta },
  { Div = Div },
  { Pandoc = Pandoc },
}
