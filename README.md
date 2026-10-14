# 🎵 MusicEnhancer

> Aplicativo desktop para Windows (10/11) focado na análise, normalização de volume e melhoria de áudio em lote de forma totalmente local e offline.

---

## 📋 Visão Geral

O **MusicEnhancer** foi projetado para resolver o problema de bibliotecas de música com volumes desequilibrados e gravações com qualidade inconsistente. Ele utiliza o padrão industrial **EBU R128 / ITU-R BS.1770** para equalizar a percepção auditiva de volume entre faixas, prevenindo *clipping* (distorções de pico) sem destruir a dinâmica do áudio ou remover informações do arquivo original.

### 🌟 Destaques do Projeto
- **Normalização EBU R128 em 2 Passagens:** Ajuste preciso de loudness (`LUFS`) e limite de True Peak (`dBTP`).
- **Processamento 100% Local e Offline:** Nenhum arquivo de áudio é enviado para servidores externos.
- **Operação Não-Destrutiva:** Mantém os arquivos originais intactos e preserva metadados (tags ID3v2, Vorbis Comments) e capas de álbum via `mutagen`.
- **Bypass Inteligente:** Identifica arquivos que já estão dentro do padrão configurado e realiza a cópia direta sem re-encodamento desnecessário (*zero generation loss*).
- **Preservação de Alta Resolução:** Mantém a taxa de amostragem (*sample rate*) e profundidade de bits (*bit-depth*) em arquivos sem perdas (FLAC / WAV).

---

## 🛠️ Stack Tecnológica

- **Python 3.10+** — Linguagem principal.
- **PySide6 (Qt for Python)** — Interface gráfica desktop (em desenvolvimento).
- **FFmpeg & FFprobe (Estáticos)** — Motor de medição e filtro de áudio (`loudnorm` / `ebur128`).
- **Mutagen** — Leitura, extração e injeção de metadados e arte de capa.
- **Pytest** — Suíte de testes automatizados de integração e unidade.

---

## 📂 Estrutura do Repositório

```text
MusicEnhancer/
├── core/                       # Núcleo de processamento de áudio
│   ├── ffmpeg_engine.py        # Subprocess wrapper do FFmpeg/FFprobe
│   ├── audio_analyzer.py       # Parser das métricas EBU R128 e pós-validação
│   └── metadata_handler.py     # Leitura e cópia de Tags/Capas via Mutagen
├── utils/                      # Utilitários e binários estáticos
│   └── bin/                    # Local dos binários ffmpeg.exe e ffprobe.exe (não versionados)
├── tests/                      # Suíte de testes automatizados (Pytest)
│   ├── test_ffmpeg_engine.py
│   ├── test_analyzer.py
│   └── test_metadata.py
├── test_cli.py                 # Script CLI para testes e validação manual
├── .gitignore                  # Arquivos e pastas ignorados pelo Git
├── requirements.txt            # Dependências Python do projeto
└── README.md                   # Documentação do projeto