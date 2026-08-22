# audiolivro

Transforma um livro — **EPUB, PDF, PDF escaneado, TXT ou Markdown** — num
audiobook com capítulos que dá para ouvir do começo ao fim. Roda
inteiramente no seu computador: nada é enviado para a nuvem, não há
cadastro, não há custo por livro e não há limite de páginas.

```bash
audiolivro ui
```

Arraste o livro para a janela, confira o que o programa entendeu, escolha
a voz, e ouça — com o texto acompanhando na tela.

> ### 🤖 Não sabe por onde começar? Peça ao Claude
>
> Copie o bloco abaixo e cole no [Claude](https://claude.ai), no ChatGPT ou
> em qualquer assistente. Ele conduz a instalação do começo ao fim, no seu
> sistema, e resolve os erros que aparecerem pelo caminho.
>
> ```
> Quero instalar e rodar o audiolivro, um programa de código aberto que
> transforma livros (EPUB, PDF, PDF escaneado, TXT) em audiobooks com
> capítulos, rodando localmente. O repositório é:
> https://github.com/backhenry/audiolivro
>
> Me guie passo a passo, um passo de cada vez, esperando eu confirmar
> antes de seguir para o próximo. Comece perguntando qual é o meu sistema
> operacional (Windows, macOS ou Linux) e se eu já tenho Python e FFmpeg
> instalados. Se eu não souber, me diga exatamente qual comando rodar para
> descobrir.
>
> Preciso que você:
> 1. me diga como instalar o Python 3.11 ou mais novo e o FFmpeg no meu
>    sistema, com os comandos exatos para copiar e colar;
> 2. me explique como baixar o repositório (com git ou baixando o ZIP);
> 3. me guie na criação do ambiente virtual e na instalação;
> 4. me faça baixar as vozes com "audiolivro baixar";
> 5. abra a interface com "audiolivro ui" e me diga o que fazer nela.
>
> Use a voz Jeff, que é o padrão e a de melhor pronúncia brasileira.
> Explique de forma simples, como se eu nunca tivesse usado um terminal.
> Se algum comando der erro, me peça a mensagem completa e me ajude a
> resolver antes de continuar.
> ```

---

> ### 🇧🇷 Qual voz usar
>
> **Jeff** (`pt_BR-jeff-medium`), do motor Piper. É a voz com pronúncia
> brasileira mais natural entre as disponíveis, e **já é o padrão** — se
> você não mexer em nada, é ela que sai.
>
> ```bash
> audiolivro gerar livro.epub                          # já usa a Jeff
> audiolivro gerar livro.epub --voz pt_BR-jeff-medium  # explícito
> ```
>
> Evite as vozes do Kokoro para português: a prosódia é melhor, mas o
> sotaque puxa para o inglês. Veja [As vozes](#as-vozes) para o porquê.

---

## Índice

- [Por que isto existe](#por-que-isto-existe)
- [O que você precisa](#o-que-você-precisa) — **macOS, Windows e Linux**
- [Instalação passo a passo](#instalação-passo-a-passo)
- [Usando pela interface](#usando-pela-interface)
- [Usando pela linha de comando](#usando-pela-linha-de-comando)
- [As vozes](#as-vozes) — **qual usar em português**
- [Corrigindo como uma palavra é lida](#corrigindo-como-uma-palavra-é-lida)
- [Tirando trechos do áudio](#tirando-trechos-do-áudio)
- [Baixando para distribuir](#baixando-para-distribuir)
- [Onde ficam os arquivos](#onde-ficam-os-arquivos)
- [O que o extrator conserta](#o-que-o-extrator-conserta)
- [Perguntas comuns](#perguntas-comuns)
- [Limitações conhecidas](#limitações-conhecidas)
- [Como o programa é organizado](#como-o-programa-é-organizado)
- [Licença](#licença)

---

## Por que isto existe

Vozes sintéticas boas e gratuitas existem há alguns anos. O que continua
faltando é o **texto**.

Um livro é escrito para o olho, que pula o que não interessa e reconstrói
o resto sem perceber que está fazendo isso. O ouvido recebe o que
mandarmos, na ordem em que mandarmos, e não pode voltar.

Jogue um PDF direto num sintetizador comum e você ouve isto:

> *"O relojoeiro trabalhava numa oficina estreita **doze** encravada entre
> — **O Nome da Rosa 137** — uma farmácia e um sobrado azul. Chamava
> **impres… sionante** … custava **erre cifrão um ponto duzentos e
> cinquenta vírgula cinquenta**, disse o **esse erre ponto** Anselmo no
> **cê a pê ponto xis i vê**."*

Cada defeito ali tem uma causa concreta: o "doze" era uma chamada de nota
de rodapé; o "O Nome da Rosa 137" era o cabeçalho da página, que a
extração entregou no meio da frase; "impres-sionante" estava partido pela
hifenização de fim de linha; o valor em reais e as abreviações nunca
foram convertidos para como se fala.

Nada disso aparece na tela. Tudo isso aparece no ouvido.

Por isso o maior subpacote deste projeto é o que cuida de **texto**, e não
o que cuida de voz.

---

## O que você precisa

| | |
|---|---|
| **Python** | 3.11 ou mais novo |
| **FFmpeg** | para montar o arquivo final |
| **Espaço** | ~200 MB para as vozes, mais o audiobook (~290 MB para 10 horas) |

Não precisa de placa de vídeo nem de internet depois da instalação. Num
Mac com chip M, a síntese roda a cerca de 20× o tempo real: um livro de 10
horas leva perto de 30 minutos.

### O que funciona em cada sistema

| | macOS | Windows | Linux |
|---|:---:|:---:|:---:|
| EPUB, PDF, TXT, Markdown | sim | sim | sim |
| Vozes Piper e Kokoro | sim | sim | sim |
| Interface e player | sim | sim | sim |
| M4B com capítulos | sim | sim | sim |
| **OCR de PDF escaneado** | sim | **não** | **não** |
| Vozes do sistema (`--motor macos`) | sim | não | não |

O desenvolvimento e os testes foram feitos em macOS com Apple Silicon.

**Sobre o OCR:** ele usa o Vision, o motor de reconhecimento de texto do
próprio macOS, que fala português e já vem instalado. Não há equivalente
embutido no Windows nem no Linux, então PDF escaneado (aquele que é foto
de página, sem texto selecionável) não é lido nesses sistemas. PDF normal,
com texto de verdade, funciona em todos.

---

## Instalação passo a passo

<details open>
<summary><b>🍎 macOS</b></summary>

**1. Instale o FFmpeg e o Python** com o [Homebrew](https://brew.sh):

```bash
brew install ffmpeg python@3.12
```

**2. Baixe o projeto:**

```bash
git clone https://github.com/backhenry/audiolivro.git
cd audiolivro
```

**3. Crie o ambiente virtual e instale.** O ambiente virtual é uma pasta
`.venv` dentro do projeto, que mantém as dependências dele separadas do
resto do sistema:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[tudo]"
```

**4. Baixe as vozes** (~190 MB, uma vez só):

```bash
.venv/bin/audiolivro baixar
```

**5. Abra a interface:**

```bash
.venv/bin/audiolivro ui
```

**6. (Opcional) Crie um atalho** para não digitar o caminho inteiro:

```bash
echo "alias audiolivro=\"$PWD/.venv/bin/audiolivro\"" >> ~/.zshrc
```

Abra uma aba nova do terminal e passe a usar só `audiolivro`.

</details>

<details>
<summary><b>🪟 Windows</b></summary>

Use o **PowerShell** (procure por "PowerShell" no menu Iniciar). Todos os
comandos abaixo são para colar lá.

**1. Instale o Python e o FFmpeg.** O jeito mais simples é o `winget`, que
já vem no Windows 10 e 11:

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

**Feche o PowerShell e abra de novo** depois disso. Sem isso, o Windows
ainda não enxerga os programas recém-instalados.

Confira que funcionou:

```powershell
python --version
ffmpeg -version
```

> Se o `winget` não existir na sua máquina, baixe o Python em
> [python.org/downloads](https://www.python.org/downloads/) — **marque a
> caixa "Add Python to PATH"** na primeira tela do instalador — e o FFmpeg
> em [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/).

**2. Baixe o projeto.** Com git:

```powershell
git clone https://github.com/backhenry/audiolivro.git
cd audiolivro
```

Sem git: clique em **Code › Download ZIP** [nesta página](https://github.com/backhenry/audiolivro),
extraia a pasta, e navegue até ela com `cd caminho\da\pasta`.

**3. Crie o ambiente virtual e instale:**

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[tudo]"
```

> A única diferença em relação ao macOS é `.venv\Scripts\` no lugar de
> `.venv/bin/`. O `[tudo]` é o mesmo: as dependências de OCR estão marcadas
> como exclusivas do macOS e o pip simplesmente as ignora aqui.

**4. Baixe as vozes** (~190 MB, uma vez só):

```powershell
.venv\Scripts\audiolivro baixar
```

**5. Abra a interface:**

```powershell
.venv\Scripts\audiolivro ui
```

**6. (Opcional) Crie um atalho** para não digitar o caminho inteiro:

```powershell
notepad $PROFILE
```

Se o Bloco de Notas perguntar se quer criar o arquivo, diga que sim. Cole
a linha abaixo, trocando o caminho pelo da sua pasta, e salve:

```powershell
function audiolivro { & "C:\caminho\para\audiolivro\.venv\Scripts\audiolivro.exe" @args }
```

Abra um PowerShell novo e passe a usar só `audiolivro`.

> Se aparecer um erro sobre execução de scripts desabilitada, rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

</details>

<details>
<summary><b>🐧 Linux</b></summary>

**1. Instale o FFmpeg e o Python** (Ubuntu/Debian):

```bash
sudo apt install ffmpeg python3.12 python3.12-venv git
```

**2. Baixe o projeto:**

```bash
git clone https://github.com/backhenry/audiolivro.git
cd audiolivro
```

**3. Crie o ambiente virtual e instale:**

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[tudo]"
```

As dependências de OCR são marcadas como exclusivas do macOS, então o pip
as ignora aqui sem reclamar.

**4. Baixe as vozes** (~190 MB, uma vez só):

```bash
.venv/bin/audiolivro baixar
```

**5. Abra a interface:**

```bash
.venv/bin/audiolivro ui
```

**6. (Opcional) Crie um atalho:**

```bash
echo "alias audiolivro=\"$PWD/.venv/bin/audiolivro\"" >> ~/.bashrc
```

</details>

### Confira que funcionou

```bash
audiolivro vozes
```

A primeira linha deve ser `piper · pt_BR-jeff-medium · Jeff` — a voz
recomendada para português, já ativa como padrão — e o rodapé deve dizer
`Motores prontos: piper, …`.

Se aparecer só `macos`, ou nenhum motor, as vozes não foram baixadas:
rode `audiolivro baixar`.

---

## Usando pela interface

```bash
audiolivro ui
```

Abre no navegador, em `http://127.0.0.1:8730`. O endereço é local: o
servidor só aceita conexões da sua própria máquina.

São três telas.

### 1. Meus livros

A lista dos seus projetos. Cada cartão mostra se o livro já tem áudio ou
é só texto, a duração, o tamanho em disco e onde você parou de ouvir.

Em **Livro novo**, arraste o arquivo para a área tracejada. Também dá
para escolher pelo Finder ou colar um caminho.

Duas caixas de opção:

- **Forçar OCR** — para PDF escaneado que o programa não detectou
  sozinho. Só marque se o resultado vier vazio.
- **Ler notas de rodapé** — por padrão as notas são descartadas, porque
  no meio de um parágrafo elas destroem a frase.

### 2. Conferir

**Esta é a tela que justifica a interface existir.** Antes de gastar
tempo gerando áudio, ela mostra o que o extrator entendeu:

- quantos capítulos, quantas falas, quanto tempo de áudio vai dar;
- quanto tempo a síntese vai levar e quantos MB o arquivo terá;
- abrindo cada capítulo, **as primeiras frases já normalizadas** — ou
  seja, exatamente como a voz vai lê-las, com os números por extenso.

É aqui que você descobre que faltou um capítulo, que a numeração das
páginas virou texto, ou que um valor saiu errado — enquanto consertar
ainda não custa nada.

Nesta tela você escolhe:

| | |
|---|---|
| **Voz** | veja a seção [As vozes](#as-vozes) |
| **Velocidade** | mexe na síntese, não na reprodução. Sai mais natural que acelerar o player depois |
| **Pausas** | multiplica todos os silêncios. "Mais longas" ajuda em texto denso |
| **Formato** | M4B tem capítulos de verdade; MP3 e M4A não |

Clique em **Gerar audiobook**. A barra mostra o progresso fala a fala e
dá para cancelar. Se você recarregar a página no meio, a interface volta
para a barra de progresso de onde parou — o estado fica no servidor.

### 3. Ouvir

O player, com a frase que está soando **destacada no texto**.

| tecla | o que faz |
|---|---|
| espaço, `k` | tocar / pausar |
| ← →, `j` `l` | 15 segundos para trás / para frente |
| ↑ ↓ | frase anterior / próxima |
| clique numa frase | pula para ela |
| **Alt + clique** | corrige como a frase é lida |

A posição é guardada sozinha. Rolar o texto com o mouse suspende a
rolagem automática por seis segundos — quem está procurando alguma coisa
não quer a página fugindo.

O M4B gerado toca no Apple Books, no Podcasts e em qualquer player comum,
com os capítulos e a posição preservados. O player daqui existe para o
que nenhum deles faz: mostrar o texto junto e deixar você corrigi-lo.

---

## Usando pela linha de comando

### Tudo de uma vez

```bash
audiolivro ouvir livro.epub
```

Extrai, sintetiza e abre o player.

### O caminho recomendado

Antes de mandar um livro de 300 páginas, ouça oito frases:

```bash
audiolivro previa livro.pdf
```

Leva segundos e toca na hora. É como se descobre que a voz não agrada ou
que o extrator comeu os diálogos.

Depois confira a estrutura e gere:

```bash
audiolivro capitulos livro.pdf     # o que o extrator encontrou
audiolivro gerar livro.pdf         # sintetiza o livro inteiro
```

### Revisar o texto antes

```bash
audiolivro extrair livro.pdf       # grava livro.livro.json
```

O arquivo gerado é um JSON legível. Abra num editor, corrija o que
quiser — um nome próprio, uma sigla — e gere a partir dele:

```bash
audiolivro gerar livro.livro.json
```

### Todos os comandos

| comando | o que faz |
|---|---|
| `ui` | abre a interface |
| `ouvir ARQUIVO` | extrai, sintetiza e abre o player |
| `previa ARQUIVO` | sintetiza algumas frases e toca |
| `extrair ARQUIVO` | gera o `livro.json` para você revisar |
| `capitulos ARQUIVO` | mostra a estrutura encontrada |
| `gerar ARQUIVO` | sintetiza o livro inteiro |
| `player ARQUIVO.m4b` | abre a interface num audiobook pronto |
| `projetos` | lista os audiobooks da sua biblioteca |
| `exportar ALVO` | converte para outro formato, para distribuir |
| `vozes` | lista as vozes disponíveis |
| `baixar [motor]` | baixa os pesos das vozes |

### Opções úteis do `gerar`

```bash
audiolivro gerar livro.epub \
  --motor piper --voz pt_BR-jeff-medium \
  --velocidade 1.05 \       # 1.0 é o natural
  --pausas 1.2 \            # afrouxa todos os silêncios em 20%
  --formato m4b \           # ou m4a, mp3, wav
  --por-capitulo \          # também gera um arquivo por capítulo
  --notas \                 # lê as notas de rodapé
  --ocr sempre              # força OCR mesmo havendo texto embutido
```

---

## As vozes

### A recomendação, direto

**Use a Jeff.** É a voz com a pronúncia brasileira mais natural entre as
disponíveis, e é o padrão do programa.

| onde | o que fazer |
|---|---|
| **Interface** | nada. "Jeff" já vem selecionado no campo *Voz* |
| **Linha de comando** | nada. `audiolivro gerar livro.epub` já usa a Jeff |
| **Para ser explícito** | `--motor piper --voz pt_BR-jeff-medium` |
| **Primeira vez** | `audiolivro baixar` traz as vozes Piper (~190 MB) |

Confira que está ativa:

```bash
audiolivro vozes
```

A primeira linha da tabela deve ser `piper · pt_BR-jeff-medium · Jeff`, e
no rodapé deve aparecer `Motores prontos: piper, …`. Se aparecer só
`macos`, as vozes ainda não foram baixadas — rode `audiolivro baixar`.

Antes de comprometer horas de síntese, ouça alguns segundos dela no seu
próprio livro:

```bash
audiolivro previa livro.epub
```

### Todas as opções

| motor | vozes pt-BR | prosódia | sotaque | velocidade |
|---|---|---|---|---|
| **`piper`** (padrão) | **Jeff**, Faber, Cadu | mais plana | brasileiro | ~20× tempo real |
| `kokoro` | Dora, Alex, Santa | a melhor | puxa para o inglês | ~9× |
| `macos` | Luciana e as do sistema | robótica | brasileiro | ~40× |

### Por que a Jeff, entre as três do Piper

As três têm pronúncia brasileira legítima — a diferença é de timbre e de
ritmo, e timbre é gosto. A Jeff ficou na frente em escuta cega de prosa
narrativa, e um número concorda com o ouvido: **no mesmo texto, a Jeff
leva 42,9 s e a Faber 36,9 s**. A Faber fala uns 15% mais rápido. Em
quinze segundos isso não importa; em dez horas, é o que separa um
narrador calmo de um apressado.

Se a Jeff soar arrastada demais para você, há duas saídas — nesta ordem:

```bash
audiolivro gerar livro.epub --velocidade 1.05          # acelera a Jeff
audiolivro gerar livro.epub --voz pt_BR-faber-medium   # troca pela Faber
```

Prefira a primeira. A `--velocidade` age na síntese, não na reprodução,
então o resultado soa melhor que acelerar o player depois.

A terceira, `pt_BR-cadu-medium`, existe para completar a lista.

### Por que o Piper é o padrão, sendo o modelo menor

O Kokoro tem a
melhor prosódia dos três — variação de entonação dentro da frase, ênfase,
respiração. Mas o modelo é treinado quase todo em inglês, e as três vozes
portuguesas entraram com pouco dado: ele acerta os fonemas do português e
erra o timbre das vogais, o que soa levemente americano. Não é problema
de fonemização, que está correta com R gutural e tudo — é o modelo
acústico, e nenhum ajuste de texto conserta.

O Piper é o contrário: cada voz foi treinada **só** em português
brasileiro, então não há inglês nenhum de onde puxar sotaque. A prosódia
é mais monótona, a pronúncia é nossa.

Num livro, sotaque pesa mais que prosódia — ele incomoda a cada frase,
durante dez horas. Daí a ordem.

Para trocar:

```bash
audiolivro gerar livro.epub --motor kokoro --voz pf_dora
```

Baixe o Kokoro antes com `audiolivro baixar kokoro` (350 MB).

> **Nota técnica.** A quarta voz pt-BR do Piper, `pt_BR-edresson-low`,
> não aparece na lista de propósito: o mapa de fonemas dela não tem o til
> combinante, então toda vogal nasal perde a nasalidade — "não" vira
> "nau", "então" vira "entau". O Piper apenas escreve uma linha de log e
> sintetiza assim mesmo.

**Dica para o motor `macos`:** baixe a voz Luciana "Aprimorada" em
*Ajustes do Sistema › Acessibilidade › Conteúdo Falado › Vozes*. É bem
melhor que a padrão, e o programa a usa sozinho. O `macos` não serve para
ouvir um romance inteiro, mas é ótimo para **revisar o texto**: sintetiza
um capítulo em menos de um segundo.

---

## Corrigindo como uma palavra é lida

Toda voz sintética erra nome próprio, sigla incomum e palavra
estrangeira. Este projeto trata isso como caso normal, não como falha.

**Na interface:** passe o mouse sobre a frase, no player, e clique no
botão **✎ editar** que aparece. O atalho é ⌥ (Option) + clique. Abre o texto que vai
para a voz — já com os números por extenso. Escreva foneticamente:

```
Kierkegaard  →  Quiérquegôr
Bordeaux     →  Bordô
```

Salve e clique em **Refazer o áudio**. Só aquela frase é sintetizada de
novo; o resto vem do cache em segundos.

**No arquivo:** abra o `livro.json` do projeto e edite o campo `texto` da
fala. O campo `exibicao` é o que aparece na tela e pode ficar como está.

Isso funciona porque o **cache é endereçado por conteúdo**: a chave é o
hash de *(motor, voz, velocidade, texto)*, sem o número da fala. Na
prática:

- corrigir um nome no capítulo 7 re-sintetiza **duas frases**, não nove
  mil;
- inserir um parágrafo no começo, que renumera tudo, não invalida nada;
- "Ele não respondeu.", que aparece dezenas de vezes num romance, é
  sintetizado uma vez só;
- comparar duas vozes no mesmo livro não faz uma invalidar a outra.

---

## Tirando trechos do áudio

Todo livro traz coisa que não se ouve: ficha catalográfica, página de
créditos, índice remissivo, bibliografia, legenda de figura. Ler tudo isso
em voz alta é o caminho mais rápido de abandonar um audiobook nos
primeiros minutos.

**Antes de gerar**, na tela de conferência, cada capítulo tem uma caixa de
seleção. Desmarque a ficha catalográfica e o índice, e eles saem do áudio.
O contador de falas passa a mostrar "4 de 14", e a estimativa de duração
cai junto.

Abrindo um capítulo, você vê **todas as frases dele**, e cada uma é
clicável: reescreva o texto que vai para a voz, ou tire a frase do áudio.
É onde se conserta o livro antes de gastar horas sintetizando — que é
melhor que descobrir o problema no meio da escuta.

**Depois de ouvir**, no player, clique numa frase segurando **Alt**. O
diálogo que abre tem três saídas:

| | |
|---|---|
| **Salvar** | reescreve o texto que vai para a voz |
| *(passe o mouse)* | o botão **✎ editar** aparece no fim da frase |
| **Não ler esta frase** | tira só ela |
| **Não ler o parágrafo** | tira o bloco inteiro, que é o caso mais comum |

O que fica de fora continua aparecendo na tela, riscado. Sumir com o
trecho esconderia justamente o que você quer conferir antes de gerar de
novo — e o botão **Voltar a ler** desfaz a qualquer momento.

Nada é apagado: o `livro.json` continua sendo o livro inteiro, e o que
muda é só o que se lê em voz alta. Depois de marcar, clique em **Refazer o
áudio**; o cache reaproveita tudo que não mudou.

---

## Baixando para distribuir

O audiobook fica em `~/Audiolivros`, mas você raramente quer o caminho: quer
o arquivo, com nome de verdade, para mandar para alguém.

No player, clique em **↓ Baixar**. Você escolhe:

| formato | quando usar |
|---|---|
| **MP3** | toca em qualquer lugar. É o que mandar para alguém |
| **M4B** | capítulos de verdade, navegáveis. Apple Books, Podcasts |
| **M4A** | igual ao M4B, sem os capítulos |
| **WAV** | sem perda e enorme. Só para reeditar em outro programa |

E se quer **um arquivo só** ou **um por capítulo**, que sai num `.zip`.

Todos saem com título, autor, álbum e número de faixa preenchidos. Sem
isso, um MP3 solto entra na biblioteca de quem recebeu como "audio", sem
autor e fora de ordem — e um audiobook de trinta capítulos embaralhado é
inutilizável.

Trocar de formato **não re-sintetiza nada**: parte do áudio pronto e é uma
passada de ffmpeg. Mesmo em dez horas, leva segundos.

Pela linha de comando:

```bash
audiolivro projetos                              # lista o que você tem
audiolivro exportar "O Nome da Rosa" -f mp3      # um MP3 do livro inteiro
audiolivro exportar "O Nome da Rosa" -f mp3 --por-capitulo
audiolivro exportar ~/livro.m4b -f mp3 -o ~/Desktop
```

Aceita tanto o nome do projeto quanto o caminho de um `.m4b` que o
`audiolivro gerar` deixou em outra pasta.

---

## Onde ficam os arquivos

Cada livro é uma pasta em `~/Audiolivros`:

```
~/Audiolivros/
  O Nome da Rosa/
    livro.json        o texto já preparado — editável à mão
    trilha.json       os tempos, para o player sincronizar
    audio.m4b         o audiobook
    posicao.json      onde a escuta parou
    original.epub     o arquivo de onde tudo veio
    exportado/        o que você baixou para distribuir
    .falas/           cache de síntese
```

Apagar um livro é apagar um diretório. Levar para outro computador é
copiar a pasta. Reabrir o mesmo EPUB cai no projeto que já existe — com
as correções que você fez nele — em vez de criar uma cópia.

Na interface, cada projeto tem dois níveis de exclusão:

- **Refazer** joga fora só o áudio e o cache. O texto revisado fica — é o
  que se quer ao trocar de voz depois de ter corrigido muitas frases.
- **Apagar** leva a pasta inteira.

As vozes ficam em `~/.cache/audiolivro` e são compartilhadas entre todos
os projetos.

---

## O que o extrator conserta

### Em qualquer formato

- **Números por extenso**, com a regra do "e" do português: `1.250` é
  "mil duzentos e cinquenta", mas `1.100` é "mil e cem";
- **concordância de gênero**: "mil e duzentas páginas", "dois milhões de
  páginas";
- **moeda, data, hora, porcentagem, ordinal, intervalo e unidade**:
  `R$ 1.250,50`, `12/03/1998`, `14h30`, `45%`, `5º`, `1914-1918`, `30 km`;
- **algarismos romanos só com contexto** — `capítulo XIV` vira "catorze",
  mas a editora `DIVA` continua DIVA;
- **abreviações** (`Sr.`, `pág.`, `séc.`, `a.C.`) sem confundir o ponto
  delas com fim de frase;
- **siglas**: `ONU` se lê como palavra, `IBGE` letra a letra, e um TÍTULO
  EM CAIXA ALTA não vira uma sequência de siglas;
- **travessão, parêntese e reticências** viram ritmo, não palavras;
- **frases longas** partidas em pontos onde um leitor humano respiraria;
- **títulos com letra espaçada**: "C A P Í T U L O  I I I", que o
  diagramador usou para dar ar à página, vira "capítulo três" em vez de
  ser soletrado letra por letra. Em PDF, os limites de palavra são
  recuperados medindo a distância entre os glifos, então "A T E L I Ê D E
  F R A G R Â N C I A" volta a ser "ATELIÊ DE FRAGRÂNCIA" e não
  "ATELIÊDEFRAGRÂNCIA".

### Em PDF

- cabeçalho, rodapé e número de página, detectados por se repetirem entre
  páginas;
- notas de rodapé, separadas por corpo menor e posição;
- palavras partidas pela hifenização — **preservando os hífens de
  verdade** (`dar-lhe`, `bem-estar`, `levá-lo`, mas juntando `clas-se` e
  `ofici-na`);
- parágrafos reconstruídos por espaçamento, recuo e linha curta;
- duas colunas, quando existem;
- o parágrafo que a virada de página partiu em dois.

### Em EPUB

Ordem do *spine* (não a dos arquivos, que costuma estar embaralhada),
notas e sumário navegável descartados, citação e lista com ritmo próprio.

### Em PDF escaneado

OCR pelo **Vision**, o motor de reconhecimento do próprio macOS — fala
português, já está instalado e não precisa de Tesseract. Daí em diante,
segue o mesmo caminho de qualquer PDF.

---

## Perguntas comuns

**Meu PDF gerou um livro vazio.**
É um PDF escaneado que não foi detectado. Marque *Forçar OCR* na
interface, ou use `--ocr sempre`. Fora do macOS não há OCR embutido.

**A síntese está lenta.**
Confira qual motor está sendo usado com `audiolivro vozes`. O Kokoro é
metade da velocidade do Piper. Você também pode limitar as threads com
`--threads`.

**Posso interromper e continuar depois?**
Sim. O cache guarda cada fala já sintetizada, então rodar de novo retoma
de onde parou.

**Dá para usar em outro idioma?**
O código é específico para português: números por extenso, abreviações,
hifenização e segmentação de frases têm regras nossas. Trocar de idioma
exige reescrever o subpacote `texto/`.

**Funciona no Linux?**
Sim, menos o OCR (que usa o Vision da Apple), a voz do sistema e o botão
"Finder". Piper e Kokoro funcionam normalmente.

**Onde estão os capítulos no MP3?**
MP3 não tem capítulos padronizados. Use M4B, ou gere `--por-capitulo`
para ter um arquivo por capítulo.

**Isso envia meus livros para algum servidor?**
Não. Toda a síntese acontece na sua máquina. A única conexão à internet é
o download inicial dos modelos de voz.

---

## Limitações conhecidas

- **`D.` continua ambíguo.** É "dom" ou "dona", e o texto não diz qual.
  Só expandimos diante de monarca (`D. Pedro II`), onde o algarismo
  romano resolve; nos outros casos a abreviação fica, porque "Dom Maria"
  é pior.
- **Tabelas não são lidas.** Uma tabela em voz alta é ruído; ela é
  descartada, não convertida.
- **Poesia** é tratada como prosa. As quebras de verso viram pausa de
  parágrafo — funciona, mas não é escansão.
- **Um idioma por livro.** Trechos em outra língua são fonemizados como
  português e saem com sotaque.
- **Não há controle de sotaque regional.** Nenhum modelo local aberto
  oferece paulista, mineiro ou nordestino como opção. O único caminho
  seria clonagem de voz a partir de uma gravação de referência.
- **O OCR erra.** Vale ouvir a prévia de um livro escaneado com mais
  atenção que a de um EPUB.

---

## Como o programa é organizado

Três estágios que não se conhecem:

```
   extrair        →        decidir        →       sintetizar
  (ingest/)               (Livro)              (voz/ + montar)
  lê o arquivo,        JSON legível com       transforma decisão
  produz blocos        o texto já pronto      em áudio e M4B
                       para ser falado
```

O **`Livro`** no meio é o artefato central. Como é um JSON comum, dá para
extrair uma vez e sintetizar várias, corrigir o texto à mão, ou trocar de
motor de voz sem reprocessar o PDF.

A **`Trilha`**, que a síntese produz, é o mapa de volta: para cada fala,
onde ela começa e quanto dura no arquivo final. É o que permite ao player
destacar a frase que está soando.

```
audiolivro/
  modelo.py        Livro, Capitulo, Bloco, Fala, Trilha — e as pausas
  projeto.py       a biblioteca: uma pasta por livro
  ingest/          um leitor por formato; convergem em BlocoBruto
    epub.py  pdf.py  ocr.py  texto.py
  texto/           a maior parte do trabalho
    coerencia.py   hifenização, cabeçalho/rodapé, reconstrução
    estrutura.py   capítulos, falas e ritmo
    sentencas.py   onde termina a frase, onde dá para respirar
    normalizar.py  do texto impresso para o texto falado
    numeros.py     por extenso em pt-BR
  voz/             motores plugáveis: piper, kokoro, macos
  sintetizar.py    orquestra síntese (paralela, com cache) e montagem
  montar.py        transmite para o ffmpeg; M4B com capítulos
  ui/              servidor local e as três telas
  cli.py
```

### Rodando os testes

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Os testes cobrem as regras que codificam julgamento e que regrediriam em
silêncio: a regra do "e" nos números, a concordância de gênero, a
decisão de manter ou juntar cada hífen de fim de linha, a detecção de
cabeçalho, a ordem das conversões numéricas e a validação de caminho na
exclusão de projetos.

### Adicionando um motor de voz

Implemente o protocolo em `voz/base.py` — `vozes()` e `sintetizar()` — e
registre em `voz/__init__.py`. Nada acima disso muda.

---

## Licença

MIT. Veja [LICENSE](LICENSE).

Os modelos de voz têm licenças próprias:
[Piper](https://github.com/rhasspy/piper) (MIT, vozes em geral CC BY) e
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0).
