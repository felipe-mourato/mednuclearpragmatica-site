# Histórico de versões do mnp-nucleo

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem [versionamento semântico](https://semver.org/lang/pt-BR/). Toda entrada diz se algum número calculado muda em relação à versão anterior.

## [0.1.0] - 2026-10-09

Primeira versão. Porta para Python a lógica do app de referência "Esvaziamento Gástrico — Cintilografia" (React/TypeScript).

### Incluído

- Leitura de DICOM não comprimido com pydicom: 8, 16 e 32 bits, com e sem sinal, rescale (inclinação e intercepto), multiframe, horário com alternativas (AcquisitionTime, ContentTime, SeriesTime, StudyTime) combinado com a data. Mensagens claras para arquivo comprimido, colorido, sem pixels ou não DICOM.
- Geometria de ROI: máscara por ponto no polígono, espelhamento para a posterior, translação limitada à imagem, simplificação do traço.
- Esvaziamento gástrico: média geométrica, correção de decaimento, retenção, esvaziamento, divisão proximal/distal por componentes principais, distribuição proximal e retenções regionais.
- Sessão por comandos JSON (usada pela ferramenta web), protocolo de reprodução e processamento em lote (`mnp-gastrico`).
- Exportação CSV e XLSX, curva em SVG e laudo HTML com as versões do software.
- Fantomas sintéticos com contagens conhecidas.

### Diferenças em relação ao app de referência

- **Espelhamento da ROI posterior:** passa a ser x' = largura − x (antes, largura − 1 − x). Com coordenadas contínuas e pixel testado pelo centro, a fórmula antiga deslocava a ROI posterior 1 pixel para a esquerda. Muda levemente as contagens posteriores.
- Pixels em precisão dupla (float64); o app de referência usava float32.
- Sobreposição proximal/distal misturada ao cinza (antes, a cor substituía o pixel na tela). Só exibição.
