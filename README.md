# MedNuclear Pragmática: site

Código do site [mednuclearpragmatica.com.br](https://mednuclearpragmatica.com.br), feito com [Quarto](https://quarto.org) e publicado no Cloudflare Pages.

Este guia é para quem não é da área de programação e usa **macOS**. Você vai usar três programas, todos gratuitos:

| Programa | Para quê |
| --- | --- |
| **Quarto** | Transforma os textos em páginas do site |
| **Visual Studio Code** (VS Code) | Editar os textos e abrir o Terminal na pasta certa |
| **GitHub Desktop** | Enviar as alterações para o GitHub, de onde o site é publicado |

---

## 1. Preparar o computador (uma vez só)

1. **Quarto.** Baixe `quarto-1.10.18-macos.pkg` em <https://github.com/quarto-dev/quarto-cli/releases/tag/v1.10.18> (role até "Assets"), abra e siga o instalador. É a mesma versão que o Cloudflare usa, para o site sair igual nos dois lugares.
2. **VS Code.** Baixe em <https://code.visualstudio.com>, arraste para Aplicativos e abra. Clique no ícone de quadradinhos na barra da esquerda (Extensões), procure **Quarto** e clique em *Install*.
3. **GitHub Desktop.** Baixe em <https://desktop.github.com>, abra e entre com a conta **felipe-mourato**.
4. **Fontes da marca (opcional).** O site carrega as fontes do Google Fonts sozinho. Se quiser vê-las também no VS Code, instale Bricolage Grotesque, Newsreader e IBM Plex Mono a partir de <https://fonts.google.com>.

## 2. Abrir o projeto

1. Descompacte o `.zip` numa pasta fixa, por exemplo `Documentos/mednuclearpragmatica-site`.
2. No VS Code: menu **File > Open Folder...** e escolha essa pasta.
3. Para abrir o Terminal já dentro da pasta: menu **Terminal > New Terminal**. Ele aparece na parte de baixo da janela. Todos os comandos deste guia são digitados ali, seguidos de Enter.

## 3. Ver o site no seu computador antes de publicar

No Terminal do VS Code, digite:

```
quarto preview
```

O navegador abre o site como ele vai ficar publicado. Enquanto o comando estiver rodando, cada vez que você salva um arquivo a página se atualiza sozinha. Para parar, clique no Terminal e aperte **Control + C**.

**Para ver também os rascunhos** (textos com `draft: true` e as páginas Ferramentas, Cursos e Newsletter):

```
quarto preview --profile rascunho
```

Rascunhos aparecem com uma faixa amarela "Rascunho" no topo e uma etiqueta "Rascunho" ao lado do título. No site publicado eles não existem: nem a página, nem o link, nem o sitemap.

## 4. Escrever um post novo

Cada post é uma **pasta** com um arquivo `index.qmd` (o texto), um `referencias.bib` (as referências) e, se houver, as imagens. Os modelos comentados estão em `_modelos/`:

| Série | Copie esta pasta | Para dentro de |
| --- | --- | --- |
| Paper comentado | `_modelos/paper-comentado` | `papers/` |
| Guia do solicitante | `_modelos/guia-do-solicitante` | `guias/` |
| Caso clínico | `_modelos/caso-clinico` | `casos/` |
| Fundamentos | `_modelos/fundamentos` | `fundamentos/` |

Passo a passo:

1. No Finder, copie a pasta do modelo (Command + C), entre na pasta da série e cole (Command + V).
2. Renomeie a pasta copiada. O nome vira o endereço do texto, então use letras minúsculas, sem acento e com hífens: `2026-11-psma-recidiva`. O endereço fica `mednuclearpragmatica.com.br/papers/2026-11-psma-recidiva/`.
3. Abra o `index.qmd` da pasta nova no VS Code. O topo do arquivo, entre as duas linhas `---`, é o **cabeçalho**: título, linha fina, data, especialidade. Cada campo está explicado ali mesmo, nos comentários (linhas que começam com `#`, que não aparecem no site).
4. Escreva no lugar das marcações `[a escrever]`. Títulos de seção começam com `## `.
5. Rode `quarto preview --profile rascunho` para ver como ficou.
6. Quando estiver pronto, apague a linha `draft: true` do cabeçalho e publique (seção 5).

O post aparece sozinho na listagem da série e entre os últimos textos da página inicial. A série, o autor e a imagem de compartilhamento já vêm da pasta da série; não precisa repetir.

### Especialidades

No cabeçalho, `categories: [Oncologia]`. As opções são **Oncologia**, **Endocrinologia** e **Cardiologia**, até duas por texto: `categories: [Oncologia, Cardiologia]`. Escreva exatamente assim, com a inicial maiúscula, para a etiqueta ganhar a cor certa.

### A ficha do estudo (Paper comentado)

No modelo, a ficha é o bloco que começa com `::: {.ficha-estudo ...}`. Cada item tem o rótulo numa linha e o conteúdo na linha seguinte, começando com `: ` (dois-pontos e espaço). Não mude os rótulos nem a ordem. O bloco `::: {.pratica}` é a caixa "O que muda na prática"; a linha que começa com `*No SUS*` sai em itálico.

### Referências

1. Abra o artigo no PubMed, clique em **Cite** e copie a referência; ou, no Zotero, clique com o botão direito no item e escolha **Exportar item > BibTeX**.
2. Cole a entrada no `referencias.bib` da pasta do post. Cada entrada começa com algo como `@article{leboulleux2022,`. Esse nome é a chave.
3. No texto, cite com a chave entre colchetes e arroba: `[@leboulleux2022]`, ou várias: `[@leboulleux2022; @leboulleux2025]`.

O site numera as citações na ordem em que aparecem e monta a lista no estilo Vancouver, no lugar da seção "Referências" do modelo.

### Imagens (Caso clínico)

Antes de usar qualquer imagem, siga a lista de conferência que está no modelo: sem dados do paciente na imagem e nunca o arquivo DICOM original (exporte uma captura em PNG ou JPG). Ponha o arquivo dentro da pasta do post e troque a linha indicada no modelo por:

```
![Descrição da imagem para quem usa leitor de tela](imagem-1.png)
```

Arquivos `.dcm` e pastas chamadas `dicom` são ignorados pelo Git e nunca sobem para o GitHub, por segurança.

### Radiofármacos e números

Para os sobrescritos, copie e cole: `⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ᵐ`. Exemplos prontos: ¹⁸F-FDG, ⁶⁸Ga-PSMA-11, ⁹⁹ᵐTc, ¹⁷⁷Lu, ¹³¹I. Atividade em MBq com mCi entre parênteses, 370 MBq (10 mCi), e decimal com vírgula.

### Imagem de compartilhamento própria (opcional)

Cada série já tem um cartão padrão (em `assets/og/`), que aparece quando alguém compartilha o link. Para um cartão com o título do post, há um gerador em `_estrutura/cartoes/gerar_cartoes.py`: acrescente uma linha na lista `CARTOES` e rode `python3 _estrutura/cartoes/gerar_cartoes.py` (exige as fontes da marca instaladas, item 4 da seção 1, e Python com Playwright: `pip3 install playwright` e depois `python3 -m playwright install chromium`). Depois ponha `image: cartao.png` no cabeçalho do post.

## 5. Publicar

### Primeira vez

**GitHub**

1. No GitHub Desktop: **File > Add Local Repository...**, escolha a pasta do projeto. Ele vai avisar que a pasta não é um repositório; clique em **create a repository** e depois em **Create Repository**.
2. Clique em **Publish repository**. Nome: `mednuclearpragmatica-site`. A opção **Keep this code private** decide se o código fica visível no GitHub; o Cloudflare funciona dos dois jeitos.

**Cloudflare Pages**

1. Em <https://dash.cloudflare.com>: **Workers & Pages > Create > Pages > Connect to Git** e autorize o GitHub.
2. Escolha o repositório `mednuclearpragmatica-site`.
3. Configure:
   - Framework preset: **None**
   - Build command: `bash build.sh`
   - Build output directory: `_site`
4. **Save and Deploy**. O primeiro build leva alguns minutos, porque o `build.sh` baixa o Quarto. Ao fim, o site fica num endereço `....pages.dev`.

**Domínio**

1. Na Cloudflare: **Add a domain** > `mednuclearpragmatica.com.br` > plano **Free**. Anote os dois servidores DNS que ela mostrar.
2. No registro.br: no domínio, **DNS > Alterar servidores DNS**, cole os dois servidores e salve. A troca pode levar algumas horas; a Cloudflare manda um e-mail quando ativar.
3. No projeto do Pages: **Custom domains > Set up a custom domain**, adicione `mednuclearpragmatica.com.br` e depois `www.mednuclearpragmatica.com.br`.

### Dali em diante

1. Edite e confira com `quarto preview`.
2. No GitHub Desktop, as alterações aparecem na coluna da esquerda. Escreva um resumo no campo **Summary** (por exemplo, "Novo guia do solicitante: PSMA") e clique em **Commit to main**.
3. Clique em **Push origin**.

A Cloudflare percebe o envio e publica sozinha em poucos minutos. Para acompanhar, veja a aba **Deployments** do projeto no Pages; se algo der errado, o log do build mostra a linha do problema.

## 6. Ativar as seções Ferramentas e Cursos

As duas páginas estão prontas, mas fora do menu e marcadas como rascunho.

**Para ativar uma delas:**

1. Abra `_quarto.yml` e procure o trecho "SEÇÕES PARA DEPOIS". Apague o `# ` do começo das duas linhas da seção (`- text: "Ferramentas"` e a `href:` logo abaixo). O hífen da linha `- text:` deve ficar exatamente embaixo do hífen de `- text: "Fundamentos"`.
2. Abra `ferramentas/index.qmd` (ou `cursos/index.qmd`) e apague a linha `draft: true`.
3. Confira com `quarto preview` e publique.

**Para acrescentar um cartão de ferramenta:** abra `ferramentas/ferramentas.yml`. O arquivo explica os campos e traz um cartão de exemplo comentado. Copie o bloco de exemplo, cole no fim, apague o `# ` do início de cada linha, preencha e apague a linha `[]` (ela só existe enquanto a lista está vazia). Se a ferramenta ainda não tiver artigo de validação, apague a linha `validacao:`; o cartão mostra "Artigo ainda não publicado".

**Para acrescentar um cartão de curso:** o mesmo, em `cursos/cursos.yml`, com o link da página da Hotmart no campo `endereco`.

Cuidado com o alinhamento nesses arquivos: as linhas de cada bloco começam com dois espaços, e o texto vai entre aspas. Se o `quarto preview` mostrar um erro com "YAML", quase sempre é um espaço a mais ou a menos.

As ferramentas em si não moram aqui: cada uma tem repositório e endereço próprios (por exemplo, `dmsa.mednuclearpragmatica.com.br`). Este site só aponta para elas.

## 7. Newsletter (desativada)

A newsletter está fora do site: não aparece no menu, no rodapé, na página inicial nem no fim dos posts. A página `newsletter.qmd` continua no projeto como rascunho, com o formulário de nome e e-mail pronto, ligado ao [Buttondown](https://buttondown.com), que guarda a lista, manda os e-mails e cuida do descadastro. Para vê-la: `quarto preview --profile rascunho`.

**Para religar, quando quiser:**

1. Crie a conta no Buttondown. O nome de usuário aparece no endereço `buttondown.com/SEU-USUARIO`.
2. Em `_quarto.yml`:
   - escreva esse nome entre as aspas da linha `buttondown-usuario: ""`;
   - apague o `# ` das duas linhas de "Newsletter" no menu (`right:`) e das duas no rodapé (`page-footer`).
3. Em `newsletter.qmd`, apague a linha `draft: true`.
4. Em `index.qmd`, no fim do arquivo, troque `::: {.mnp-chamada .content-hidden}` por `::: {.mnp-chamada}`. Isso devolve a chamada da newsletter à página inicial.
5. Para o botão "Receber a newsletter" voltar ao fim de cada post: em `_estrutura/mnp.lua`, troque `local NEWSLETTER_ATIVA = false` por `local NEWSLETTER_ATIVA = true`.
6. Confira com `quarto preview` e publique.

Como funciona depois de ligada: quem se inscreve recebe um e-mail do Buttondown para confirmar; todo e-mail enviado traz um link para sair. Para mandar um e-mail automático a cada texto novo, a função RSS-to-email do Buttondown (paga) lê o feed `https://mednuclearpragmatica.com.br/todos.xml`, que o site já gera. O nome fica guardado como `nome` e entra no e-mail com `{{ subscriber.metadata.nome }}`.

## 8. CSS da marca para as ferramentas

`assets/marca/mnp-marca.css` tem as cores, as fontes, o tema claro e escuro e algumas peças prontas (cabeçalho com logo, barra térmica, aviso, botões). Depois de publicado, qualquer ferramenta pode usá-lo com:

```html
<link rel="stylesheet" href="https://mednuclearpragmatica.com.br/assets/marca/mnp-marca.css">
```

Os logos ficam em `https://mednuclearpragmatica.com.br/assets/logos/`. Se mudar uma cor, mude também em `estilos/mnp-claro.scss` e `estilos/mnp-escuro.scss`, que são o tema do site.

## 9. Mapa dos arquivos

| Arquivo ou pasta | O que é |
| --- | --- |
| `index.qmd` | Página inicial |
| `papers/`, `guias/`, `casos/`, `fundamentos/` | As séries. O `index.qmd` de cada uma é a listagem; cada subpasta é um post |
| `sobre.qmd`, `todos.qmd`, `404.qmd` | Páginas fixas (`todos.qmd` lista todos os textos e gera o feed RSS do site) |
| `newsletter.qmd` | Página da newsletter, desativada (rascunho) |
| `ferramentas/`, `cursos/` | Seções para depois (rascunho) |
| `_modelos/` | Modelos comentados de post. Não aparecem no site |
| `_quarto.yml` | Configuração geral: menu, rodapé, endereço do site |
| `estilos/` | Tema do site (cores e tipografia) e o estilo de referências Vancouver |
| `assets/` | Logos, favicon, cartões de compartilhamento e o CSS da marca |
| `_estrutura/` | Peças internas do site (cabeçalho dos artigos, listagens, cartões). Raramente precisa mexer |
| `build.sh` | Script que o Cloudflare roda para gerar o site |
| `_site/` | Site gerado. Não vai para o GitHub; é refeito a cada publicação |

## 10. Manutenção

- **Atualizar o Quarto do site:** em `build.sh`, troque o número em `QUARTO_VERSION` por uma versão estável recente (<https://quarto.org/docs/download/>), instale a mesma versão no Mac e confira com `quarto preview` antes de publicar.
- **Testar o build como o Cloudflare faz** (opcional): o `build.sh` foi feito para Linux, então no Mac use só `quarto render` para conferir se o site gera sem erros.
