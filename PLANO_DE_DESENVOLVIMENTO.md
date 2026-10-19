# PLANO DE DESENVOLVIMENTO — MusicEnhancer

> Documento de referência reconstruído a partir do estado **real** do repositório.
> Base de análise: branch `main`, commit `5d99b44`, working tree limpo.
> Suíte executada na data da análise: `117 passed in ~4,5 s` (pytest, ambiente `.venv`).
> Escopo deste documento: **análise e planejamento apenas** — nenhuma funcionalidade foi implementada.

---

## A. Visão geral

**Objetivo:** aplicativo desktop para Windows 10/11 que equilibra o volume de bibliotecas de música
(normalização EBU R128 / ITU-R BS.1770) em lote, com processamento não-destrutivo, preservação de
qualidade e de metadados, funcionando 100% local e offline.

**Público-alvo:** usuários Windows com bibliotecas pessoais (MP3/FLAC/WAV/M4A) que precisam
padronizar loudness para streaming/contexto de escuta, sem reprocessar ou degradar arquivos que já
estão dentro do padrão, e sem enviar áudio para serviços externos.

**Princípios técnicos:**

1. **Offline primeiro** — todo o processamento ocorre em FFmpeg local; nenhum recurso exige internet.
2. **Não-destrutivo** — o arquivo original nunca é modificado; a saída é publicada somente após
   geração e validação (arquivo temporário + `os.replace`).
3. **Preservação de qualidade** — taxa de amostragem, canais, layout e profundidade de bits são
   preservados dentro das limitações do formato de destino; bypass evita gerações de reencode.
4. **Processamento em lote tolerante a falhas** — a falha de uma faixa não interrompe o lote.
5. **Código testável** — núcleo isolado de UI (PySide6 via `ui/`), suíte pytest com mocks e
   integração real com FFmpeg.
6. **Base para IA local futura** — a arquitetura em camadas (`core` / `ui` / `utils`) deixa o
   pipeline de aprimoramento de IA como extensão do núcleo, sem dependência de nuvem.

---

## B. Estado atual

### B.1 Funcionalidades implementadas (com evidências)

| Área | Funcionalidade | Evidência |
|---|---|---|
| Núcleo FFmpeg | Localização de binários (`utils/bin` com fallback para `PATH`), wrapper de subprocesso com erros tipados | `core/ffmpeg_engine.py` (`_find_binary`, `_run`) |
| Núcleo FFmpeg | Medição EBU R128 via `ebur128` (I, TP, LRA, Threshold) com rejeição de valores não finitos/fora de faixa | `analyze_loudness` |
| Núcleo FFmpeg | Medição via **1º passe do `loudnorm` com `print_format=json`** e 2º passe com `measured_*`, `offset`, `linear=true/false` (decisão linear × dinâmica baseada em ganho × True Peak e LRA) | `analyze_loudnorm`, `_linear_normalization_possible`, `_read_normalization_type` |
| Núcleo FFmpeg | Bypass (cópia sem reencode) quando loudness/TP estão dentro dos **alvos do usuário** e o contêiner é o mesmo | `should_bypass` |
| Núcleo FFmpeg | Codecs de destino: MP3 (`libmp3lame`), AAC/M4A (`aac`), WAV (`pcm_s16le/s24le/s32le/f32le/f64le` — inteiro e float diferenciados), FLAC 16/24 bits (`-bits_per_raw_sample`) | `_select_wav_codec`, `_select_flac_bit_depth`, `_codec_arguments` |
| Núcleo FFmpeg | Preservação de taxa de amostragem, canais e layout (`-ar`, `-ac`, `-channel_layout`); downmix MP3 >2 canais com aviso | `_codec_arguments` |
| Núcleo FFmpeg | Validação da saída com ffprobe (taxa, canais, layout, bit-depth em formatos sem perdas, duração com tolerância) | `core/audio_analyzer.py` (`validate_export`) |
| Núcleo FFmpeg | Escrita em arquivo temporário + validação + `os.replace`; limpeza de temporários em falha | `normalize` (bloco `try/finally`) |
| Núcleo FFmpeg | Exceções específicas (`FFmpegExecutionError`, `LoudnessAnalysisError`, `AudioValidationError`, `UnsupportedAudioFormatError`) | `core/exceptions.py` |
| Metadados | Cópia de tags ID3v2.3 (MP3), Vorbis Comments + capas (FLAC), fallback genérico (M4A/MP4/Ogg); falha de metadados é **não-crítica** e comunicada | `core/metadata_handler.py`, `NormalizationResult.warnings`/`metadata_preserved` |
| Configurações | `core/settings.py`: sanitização/validação (alvos EBU R128), `config.json` portátil, pastas por SO | `DEFAULT_CONFIG`, `sanitize_config`, `load_config` |
| UI/Worker | Processamento em lote assíncrono (QThreadPool), continuidade após falha, manifest `.musicenhancer_manifest.json` que evita reprocessamento com alvos idênticos (inclui LRA), política de sobrescrita `rename/replace/skip` + `apply_all` | `ui/workers.py`, `ui/main_window.py` (`OverwriteDialog`) |
| UI | Janela principal (tabela de faixas, inspetor com métricas/presets/avançado incl. LRA), drag & drop, atalhos, cancelamento, status badges, tema escuro | `ui/main_window.py`, `ui/music_table.py`, `ui/inspector_panel.py`, `ui/styles.py` |
| Logging | Log global centralizado (console + `musicenhancer.log`) | `utils/logger.py`, `main.py` |
| CLI manual | Validação ponta a ponta do engine via linha de comando | `test_cli.py` (script manual, fora da suíte pytest) |

**Commits de referência confirmados no histórico:**
- Etapa 1: `ff60401` — *fix(core,ui): corrige inicialização, resolução de atalhos e sistema de configurações*.
- Etapa 2: `5d99b44` — *feat(core,ui): implementa normalização EBU R128 em 2 passos com preservação técnica* (11 arquivos, +1.796/−200).
- Commit `e435966` foi higienização do repositório (remoção de artefatos de ferramentas, ajustes em `metadata_handler`).

### B.2 Situação dos testes

- Suíte: `tests/` com `pytest` (`testpaths = tests` em `pytest.ini`).
- Contagem confirmada: **117 passed** no ambiente `.venv` (unitários com mocks + integração com
  FFmpeg real usando arquivos sintéticos gerados localmente; testes de integração são *skipped*
  se o FFmpeg não estiver disponível — todos executados com sucesso nesta análise).
- Cobertura funcional dos testes: alvos personalizados, parsing do relatório JSON do `loudnorm`
  (incluindo medições ausentes/inválidas), decisão de bypass, codecs WAV 16/24/32 int e float,
  FLAC 16/24, preservação de taxa/canais, falhas de subprocesso/arquivo corrompido/silêncio,
  metadados não críticos, continuidade do lote, e propriedades reais dos arquivos de saída.
- Scripts **fora** da suíte: `test_ui.py` e `test_cli.py` na raiz (validação manual; `pytest.ini`
  não os coleta).

### B.3 Infraestrutura e documentação

- **CI:** não existe (sem `.github/workflows`).
- **Empacotamento:** não existe (sem `.spec`, sem `build/`, sem ícone `.ico`). O `.gitignore` já
  reserva `build/`, `dist/`, `*.spec` e `utils/bin/*.exe` (com exceção de `.gitkeep`), mas o
  diretório `utils/bin` **não existe hoje** — o funcionamento offline depende do FFmpeg no `PATH`
  da máquina.
- **IA local:** nenhum código relacionado existe no repositório. O `opencode.json` é apenas
  configuração do agente de desenvolvimento, não do aplicativo.
- A única documentação é o `README.md`, que está **desatualizado**: a seção “Estrutura” lista apenas
  3 testes (a suíte tem hoje 7 arquivos + `core/exceptions.py` + `ui/` inteiro), marca o PySide6
  como “em desenvolvimento” e não menciona o fluxo de duas passagens com validação.

### B.4 Lacunas funcionais confirmadas no código

1. **Progresso por faixa não está operante:** `BatchSignals.track_progress` existe
   (`ui/workers.py`), mas nunca é emitido, e `MainWindow.update_track_progress`
   (`ui/main_window.py`) não está conectado a nenhum worker. Hoje só existe progresso geral.
2. **Status “Pico Elevado” (`peak_warn`) não tem origem real:** o status e o estilo existem
   (`ui/constants.py`, `ui/styles.py`), mas aparecem apenas nos `MOCK_TRACKS` de demonstração
   (`ui/music_table.py`); a análise real nunca o produz, mesmo com TP > −1,0 dBTP.
3. **Detalhes do resultado não chegam à UI:** `normalization_type` (linear/dinâmico), avisos de
   metadados e resultado da validação ficam no resultado/manifesto/log, não na linha da tabela.
4. **Manifesto reprocessa indevidamente em um caso:** a entrada é reaproveitada apenas se o destino
   existir e os alvos coincidirem; não há verificação de integridade do destino.

---

## C. Decisões técnicas consolidadas (a preservar)

1. **Stack:** Python 3.10+ · PySide6 (Qt for Python) · FFmpeg/FFprobe estáticos via subprocess ·
   Mutagen · pytest. Nenhuma dependência de nuvem.
2. **Normalização:** duas passagens de `loudnorm`; 1º passe com `print_format=json` e uso de
   `measured_*` + `target_offset` no 2º passe; `linear=true` com `linear=false` quando o ganho
   viola True Peak/LRA; métricas são validadas (finitas e dentro dos intervalos aceitos pelo
   filtro: I −70…−5, TP −9…0, LRA 1…50) **antes** de montar o comando final.
3. **Padrões de alvo:** `-14 LUFS / -1 dBTP / 11 LU` como padrão único definido em
   `core.settings.DEFAULT_CONFIG` (`target_loudness`, `target_true_peak`, `target_lra`) — motores
   de UI e núcleo leem daqui, sem duplicar valores padrão em módulos.
4. **Bypass:** exigência de contêiner idêntico + tolerância de ±0,5 LU + TP ≤ alvo; alvos
   personalizados do usuário sempre respeitados.
5. **Codecs/formatos:** MP3 (bitrate clampado por heurística `_audio_bitrate`), AAC/M4A,
   WAV com mapeamento exato da representação PCM (inteiro/floating, 16/24/32/64),
   FLAC com `s16/s32` + `-bits_per_raw_sample` (máximo do formato: 24 bits, com aviso).
6. **Integridade:** temporário no diretório de destino (mesma extensão), validação ffprobe da
   saída e só então `os.replace`; destino pré-existente preservado em caso de falha.
7. **Erros:** exceções tipadas em `core/exceptions.py` subclassificando `RuntimeError`/`ValueError`
   (compatível com o tratamento já existente nos workers); falha de metadados nunca invalida um
   áudio validado — vira aviso.
8. **Metadados:** Mutagen com caminhos dedicados para MP3 (ID3v2.3) e FLAC (Vorbis + capas) e
   fallback genérico; determinístico na ordem atual (MP3 → FLAC → genérico).
9. **Manifesto JSON no diretório de saída** com alvos aplicados, tipo de normalização e flag de
   metadados, gravado por escrita temporária; usado para pular faixas já processadas com os
   mesmos alvos.
10. **Persistência dupla** (decisão existente, mantida): `QSettings` para estado da janela/prefs
    rápidas + `core/settings.py` (`config.json` em AppData ou portátil na raiz) para os valores
    de domínio.
11. **Concorrência:** `QThreadPool` com 2–4 threads (mínimo 2, máximo 4), workers QRunnable com
    sinais Qt e cancelamento cooperativo.
12. **Logging:** centralizado em `utils/logger.py` (arquivo reaberto em modo “w” por sessão).

---

## D. Pendências identificadas

Somente itens **confirmados** na seção B. Sem ordem artificial: a prioridade é pela justificativa.

| # | Pendência | Prioridade | Justificativa |
|---|---|---|---|
| D1 | Emitir progresso por faixa e conectar à UI (`track_progress` morto, `update_track_progress` não conectado) | **Alta** | “Processamento em lote com acompanhamento de progresso” é objetivo declarado; a infraestrutura já existe, falta a conexão final. |
| D2 | Produzir o status `peak_warn` real na análise (TP alvo configurável) | **Alta** | Estados de UI são objetivos da interface; hoje são demonstração apenas. Depende dos alvos configurados (já disponíveis no `AnalysisWorker`). |
| D3 | Exibir detalhes do resultado por faixa (tipo de normalização, avisos de metadados, falha de validação) | Média | Torna visível o que hoje só existe no log/manifesto; melhora a confiança do usuário sem mudar o núcleo. |
| D4 | Empacotar FFmpeg/FFprobe (`utils/bin`) e tornar o funcionamento offline independente do `PATH` | **Alta** | Requisito offline central; hoje o app só roda se o FFmpeg estiver no `PATH`. `.gitignore` já trata os binários — falta o procedimento. |
| D5 | Empacotamento/distribuição do aplicativo Windows (PyInstaller + ícone + versão) | Média | Bloqueada por D4 (os binários precisam existir/ser localizados); depende de decisão de licenciamento do build do FFmpeg. |
| D6 | CI (GitHub Actions) executando a suíte offline (instalando FFmpeg no runner) | Média | Protege as 117 regressões antes de qualquer distribuição; custo baixo, ganho alto. |
| D7 | Atualizar `README.md` e criar documentação de arquitetura | Média | README desatualizado desorienta contribuidores/outras IAs; o plano assume “consultar docs” que hoje incompletas. |
| D8 | Verificação de integridade no reaproveitamento do manifesto (hash do destino ou mtime+tamanho) | Média | Objetivo “evitar reprocessamento” não pode pular faixas corrompidas manualmente; trade-off de custo de I/O exige decisão. |
| D9 | Cobertura documentada/testada de metadados M4A (capas `covr` via caminho genérico) | Baixa | Funcionalidade pode já funcionar (caminho genérico copia chaves), mas não há teste dedicado. |
| D10 | Regularizar scripts da raiz (`test_cli.py`, `test_ui.py`) como ferramentas manuais documentadas (ou mover para `scripts/`) | Baixa | São úteis, mas ficam fora do `testpaths` do pytest; documentar evita confusão de cobertura. |
| D11 | Aprimoramento de áudio com IA executada localmente | **Bloqueada por decisão** | Nenhum código existe; exige escolha de engine/modelo e estratégia de distribuição de modelos offline antes de qualquer estimativa. |

---

## E. Roadmap por etapas

### Etapa 3 — Estabilização do processamento em lote e feedback na UI

- **Objetivo:** completar o acompanhamento de progresso e os estados de faixa no lote, usando a
  infraestrutura já existente (sem novas arquiteturas).
- **Funcionalidades:** progresso percentual por faixa; status `peak_warn` real na análise
  (mouse-over com aviso de risco no reencode); exibição de avisos de metadados e tipo de
  normalização na linha/status; cancelamento verificado durante os novos estados.
- **Arquivos:** `ui/workers.py` (emitir `track_progress`; `AnalysisWorker` com alvos), `ui/main_window.py`
  (conectar `track_progress`/exibição de detalhes), `ui/music_table.py`, `ui/constants.py` (textos),
  `tests/test_workers.py`, `tests/test_ffmpeg_engine.py`.
- **Dependências:** Etapas 1 e 2 concluídas (alvos configuráveis já retroalimentam o cálculo).
- **Critérios de conclusão:** progresso por faixa visível 0–100% durante o lote; faixa com
  TP > alvo é sinalizada `peak_warn` após análise; avisos de metadados visíveis por faixa;
  suíte completa verde.
- **Testes:** worker emitindo `track_progress` para Fake agregador; análise marcando `peak_warn`
  com alvos personalizados; testes de regressão dos 117 existentes.
- **Riscos:** escolha do cálculo do percentual (progresso percentual requer peso por duração ou
  uso de `-progress` do FFmpeg) — manter simples inicialmente (faixas concluídas/falhas) ou
  adotar `-progress`; evitar excesso de sinais Qt por segundo (signal flooding em UI).

### Etapa 4 — Empacotamento do FFmpeg e funcionamento offline garantido

- **Objetivo:** garantir que o aplicativo rode sem FFmpeg instalado, com binários estáticos dentro
  do projeto, seguindo o contrato de detecção já implementado.
- **Funcionalidades:** procedimento/scripts para baixar (uma vez, na máquina de build) ou copiar
  `ffmpeg.exe`/`ffprobe.exe` para `utils/bin`; decisão sobre versionar ou usar instalador externo;
  validação de versão mínima; mensagens de erro amigáveis.
- **Arquivos:** `utils/bin/` (não versionado ou Git LFS — ver incertezas), `core/ffmpeg_engine.py`
  (pouco ou nada), `README.md`, eventual `scripts/setup_ffmpeg.ps1` e `docs/`.
- **Dependências:** nenhuma code-change além de scripts/docs; deve vir **antes da Etapa 6**.
- **Critérios de conclusão:** rodar o aplicativo/suite em máquina limpa (sem FFmpeg no PATH) após
  colocar os binários em `utils/bin`; documentação do procedimento.
- **Testes:** testes de integração forçando o uso dos binários empacotados; teste de ausência
  (mensagem clara de erro).
- **Riscos:** licenciamento (builds “essentials” do gyan.dev são GPL — revisar termos antes de
  distribuir); tamanho do repositório/CI se versionar binários.

### Etapa 5 — Qualidade contínua e documentação

- **Objetivo:** proteger o funcionamento verificável com CI e deixar a documentação em dia.
- **Funcionalidades:** GitHub Actions rodando pytest (instala dependências + FFmpeg no runner),
  artefato de cache; atualização do README (estrutura real, testes, uso, requisitos); documento de
  arquitetura (`docs/ARQUITETURA.md`) descrevendo o fluxo de 2 passagens, validação e UI.
- **Arquivos:** `.github/workflows/*.yml` (novo), `README.md`, `docs/`, `pytest.ini` (ajuste opcional).
- **Dependências:** Etapa 4 facilita (FFmpeg empacotado/pipeline conhecido), mas não é bloqueante —
  o runner pode instalar FFmpeg por outra via.
- **Critérios de conclusão:** pipeline verde na `main`; README reflete 100% da estrutura atual;
  arquitetura documentada.
- **Testes:** a própria suíte (117+); job falha em qualquer regressão.
- **Riscos:** versão de Python no runner × `.venv` local (o ambiente local usa Python 3.14;
  README declara 3.10+ — definir a versão suportada oficialmente).

### Etapa 6 — Empacotamento e distribuição Windows

- **Objetivo:** entregar executável instalável/portátil.
- **Funcionalidades:** build PyInstaller (one-folder ou one-file), ícone `.ico`, atualização de
  versão coerente com `main.py` (`0.3.0`), empacotar FFmpeg da Etapa 4 dentro do bundle,
  instalador opcional (NSIS/Inno).
- **Arquivos:** novo `musicenhancer.spec` (ou settings no pyproject), `main.py` (path de recursos),
  `core/ffmpeg_engine.py` (ajustar resolução de `utils/bin` quando executável congelado — path
  de `sys._MEIPASS`).
- **Dependências:** **Etapa 4 (obrigatória)**, Etapa 5 recomendada (CI pode buildar o release).
- **Critérios de conclusão:** executável roda em Windows limpo, normaliza WAV/FLAC/MP3 reais,
  mantém metadados e bypass; sem necessidade de FFmpeg instalado.
- **Testes:** smoke test pós-build (estilo do script manual `test_ui.py`); suíte verde antes do build.
- **Riscos:** tamanho do bundle com FFmpeg; assinatura de código (se exigida); paths congelados
  (cuidado com `Path(__file__)` em `utils/logger.py` e `core/settings.py` no modo portátil).

### Etapa 7 — Aprimoramento de áudio com IA local (blocada por decisão)

- **Objetivo:** funcionalidade de melhoria de áudio 100% offline declarada no objetivo do projeto.
- **Funcionalidades futuras (placeholders até decisão):** seleção de modelo local (ex. ONNX),
  pipeline como filtro opcional antes/depois da normalização, batch worker dedicado com
  GPU/CPU, gestão de modelos no diretório do usuário.
- **Arquivos:** ainda inexistente (caminho natural: `core/enhancer/` ou similar integrado ao
  `FFmpegEngine` e `BatchWorker`).
- **Dependências:** decisão humana sobre engine/modelo/estratégia de distribuição (ver seção H e incertezas);
  Etapas 3–6 recomendadas antes (feedback sólido primeiro).
- **Critérios de conclusão:** a definir após decisão de escopo.
- **Testes:** a definir (integração com modelos sintéticos/mock; avaliação subjetiva exige
  protocolo próprio).
- **Riscos:** dependências pesadas (onnxruntime/torch), consumo de RAM/GPU, licenças de modelos,
  tamanho de download de modelos — todos contrários ao princípio offline se mal empacotados.

> Não há necessidade de etapa artificial entre 3 e 4: a estabilização (3) é curta e independente;
> o empacotamento do FFmpeg (4) não depende dela, mas convém iniciá-la rapidamente.

---

## F. Estratégia de testes e qualidade

1. **Regressão (obrigatória em toda PR/etapa):** suíte completa `pytest` verde — hoje 117 testes
   (unitários com mocks dentro de `tests/` + integração real). Nenhum teste pode ser removido ou
   enfraquecido para aprovar uma etapa; quando o comportamento muda de propósito, o teste antigo é
   atualizado com justificativa no relatório da etapa.
2. **Integração real (FFmpeg):** os testes de `tests/test_integration_audio.py` usam arquivos
   sintéticos gerados na hora (sine/anullsrc) e são **skipped** se o FFmpeg não estiver disponível
   — garantem codificação real, propriedades de saída via ffprobe e comportamento do bypass.
   Critério: sempre rodar a integração completa na máquina local antes de cada commit de etapa.
3. **Qualidade de áudio:** critérios verificáveis, não subjetivos: loudness de saída dentro de
   tolerância do alvo (ex.: ±1,0 LU no teste de integração), TP ≤ alvo, bit-depth/taxa/canais
   preservados, duração dentro da tolerância de padding, e decisão de bypass quando aplicável.
4. **Preservação de metadados:** testes unitários com mocks (Mutagen) para MP3/FLAC/genérico +
   integração real validando tags (FLAC) e fluxo de falha não-crítica (`metadata_preserved=False`
   + `warnings`).
5. **Funcionamento offline:** proibido qualquer download em runtime; testes não fazem rede;
   a validação de “offline” é garantida por (a) FFmpeg empacotado (Etapa 4) e (b) ausência de
   dependências de rede no código (`grep` de revisão).
6. **UI:** verificação manual (script `test_ui.py`) nas mudanças visuais; regressão
   visual não automatizada hoje — aceitável nas etapas atuais.
7. **Critérios de commit:** nenhum `pytest` com falha; mensagens convencionais (feat/fix/docs/refactor
   + escopo), histórico por etapa.

---

## G. GitHub e documentação

- **Commits:** mensagens convencionais em PT-BR, um commit (ou pequena sequência) por etapa, com
  relatório no corpo; nenhuma força-push; `git push` **somente com autorização explícita**.
- **Branch:** trabalhar em `main` para etapas (padrão atual) ou abrir branch `etapa-3` se a
  coordenação preferir (decisão a confirmar).
- **Documentação viva:** `README.md` (visão, uso, requisitos), `PLANO_DE_DESENVOLVIMENTO.md`
  (este documento — atualizar status/tick de etapas concluídas), `docs/ARQUITETURA.md` (Etapa 5),
  relatórios de etapa embutidos nos commits.
- **Critério de etapa concluída:** (1) todos os critérios objetivos da seção E atendidos e
  evidenciados; (2) suíte completa verde na máquina local (incluindo integração com FFmpeg);
  (3) revisão do `git diff` sem alterações acidentais; (4) commit local da etapa; (5) README/este
  plano atualizados, quando a etapa alterar comportamento documentado.
- **Histórico de referência:** `ff60401` (Etapa 1), `5d99b44` (Etapa 2) — usar como padrão de
  granularidade e mensagens.

---

## H. Próxima etapa recomendada

**Etapa 3 — Estabilização do processamento em lote e feedback na UI.**

Justificativa baseada em evidências, não em preferência:

1. É a pendência com **menor custo e maior retorno imediato**: os sinais de progresso por faixa
   já existem (`BatchSignals.track_progress`), basta emitir e conectar; os estados de UI
   (`peak_warn`) já existem nos templates de estilo; os alvos já são computados no
   `AnalysisWorker`.
2. Prepara o terreno da Etapa 4–6 com o produto **visível e utilizável**: distribuir um
   executável (6) de um lote sem progresso por faixa seria entregar uma experiência aquém das
   metas já implementadas no núcleo.
3. Reduz o risco de regressão de UI antes de empacotar: a Etapa 6 congela paths e distribui o
   produto — mudanças de comportamento em lote após empacotar teriam custo de re-spin de build.
4. Não depende de nenhuma decisão humana pendente (capas M4A, IA, licenciamento FFmpeg), ao
   contrário das Etapas 4 (licença), 6 (assinatura/instalador) e 7 (engine IA).

---

*Documento gerado somente com base no repositório em `main` @ `5d99b44`. Nenhuma funcionalidade
foi implementada ou alterada; nenhum commit foi criado (o arquivo é novo e não rastreado).*
