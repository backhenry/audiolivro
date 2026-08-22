/* A interface, em três telas: abrir → preparar → ouvir.
 *
 * O estado de verdade mora no servidor — qual livro está aberto, se já
 * foi sintetizado, onde parou a escuta. O navegador só desenha. Isso é o
 * que faz recarregar a página no meio de uma síntese de duas horas
 * mostrar a barra de progresso continuando, em vez de voltar para a tela
 * inicial como se nada estivesse acontecendo.
 */

const $ = (id) => document.getElementById(id);
const som = $("som");

const app = {
  livro: null,     // resumo vindo de /api/estado
  texto: null,     // livro achatado, só depois de sintetizar
  falas: [],       // ordenadas por início; o índice do destaque
  capitulos: [],
  atual: -1,
  capAtual: -1,
  seguirTexto: true,
  tarefa: null,
};

iniciar();

async function iniciar() {
  ligarAbrir();
  ligarListaDeProjetos();
  ligarPreparar();
  ligarOuvir();
  await sincronizar();
}

/* Pergunta ao servidor o que existe e mostra a tela certa.
 *
 * A tela inicial é *sempre* a lista de projetos. A versão anterior
 * entrava direto no último livro aberto, e abrir a interface caía no
 * livro de ontem sem lista e sem saída óbvia. Entrar num projeto passou a
 * ser sempre um clique.
 *
 * A única exceção é a síntese em andamento: aí há trabalho acontecendo
 * que o usuário não pode perder de vista, e voltar para a tela de
 * progresso é o que ele espera. */
async function sincronizar() {
  const estado = await pedir("/api/estado");
  preencherVozes(estado.vozes, estado.motores);
  // A lista de extensões aceitas tem apelidos (.md, .mdown, .markdown)
  // que não dizem nada a mais para quem lê. O texto fixo do HTML é mais
  // útil; só a guardamos para validar a extensão antes de subir.
  app.formatos = estado.formatos;
  app.projetos = estado.projetos;
  // Botão que não faz nada é pior que botão ausente: quem clica conclui
  // que o programa está quebrado, não que o recurso não existe aqui.
  $("procurar").hidden = !estado.seletor_nativo;
  $("o-revelar").hidden = !estado.revelar;
  const ocr = $("ocr").closest("label");
  ocr.title = estado.ocr ? "" : "OCR indisponível neste sistema (usa o Vision do macOS)";
  ocr.style.opacity = estado.ocr ? "" : ".45";
  $("ocr").disabled = !estado.ocr;
  $("onde-fica").textContent = `Os projetos ficam em ${estado.biblioteca}`;
  $("p-destino").textContent = `Os projetos ficam em ${estado.biblioteca}`;

  if (estado.retomar && estado.tarefa) {
    const detalhe = await pedir("/api/projetos/abrir", { nome: estado.retomar });
    entrarEmPreparar(detalhe);
    $("gerar").disabled = true;
    $("cancelar").hidden = false;
    $("progresso").hidden = false;
    app.tarefa = estado.tarefa.id;
    acompanhar(estado.tarefa.id);
    return;
  }

  desenharProjetos(estado.projetos);
  mostrar("abrir");
}

function desenharProjetos(projetos) {
  $("biblioteca").hidden = projetos.length === 0;
  $("novo").open = projetos.length === 0;
  $("conta-projetos").textContent =
    projetos.length === 1 ? "1 livro" : `${projetos.length} livros`;

  $("lista-projetos").innerHTML = projetos.map((p) => {
    const selo = p.pronto
      ? `<span class="selo pronto">pronto</span>`
      : `<span class="selo rascunho">só texto</span>`;
    const partes = [
      p.autor,
      p.pronto ? hms(p.duracao) : `${p.capitulos} capítulos`,
      p.pronto ? p.voz : `${p.falas} falas`,
      tamanho(p.tamanho),
    ].filter(Boolean);
    // Onde a escuta parou só vale mostrar se já saiu do começo e ainda
    // não chegou ao fim — nos extremos é ruído.
    const parcial = p.pronto && p.posicao > 30 && p.posicao < p.duracao - 30
      ? `<span class="sep">·</span><span>parou em ${hms(p.posicao)}</span>` : "";
    return `<li class="projeto" data-nome="${escapar(p.nome)}">
      <div class="corpo" data-acao="abrir">
        <div class="titulo">${escapar(p.titulo)}</div>
        <div class="linha2">${
          partes.map(escapar).map((t) => `<span>${t}</span>`).join('<span class="sep">·</span>')
        }${parcial}</div>
      </div>
      ${selo}
      <div class="acoes-projeto">
        ${p.pronto ? '<button data-acao="finder" title="Mostrar no Finder">Finder</button>' : ""}
        ${p.pronto ? '<button data-acao="limpar" title="Apagar só o áudio e o cache, mantendo o texto revisado">Refazer</button>' : ""}
        <button class="perigo" data-acao="apagar" title="Apagar o projeto inteiro">Apagar</button>
      </div>
    </li>`;
  }).join("") || `<p class="vazio">Nenhum livro ainda.</p>`;
}

function mostrar(tela) {
  for (const nome of ["abrir", "preparar", "ouvir"]) $(nome).hidden = nome !== tela;
}

/* ================================================================ abrir */

function ligarAbrir() {
  const solta = $("solta");
  const entrada = $("arquivo");

  solta.onclick = () => entrada.click();
  entrada.onchange = () => entrada.files[0] && enviar(entrada.files[0]);

  // `dragover` precisa do preventDefault, senão o navegador abre o
  // arquivo numa aba nova e a página some junto com o estado.
  for (const evento of ["dragenter", "dragover"]) {
    solta.addEventListener(evento, (e) => {
      e.preventDefault();
      solta.classList.add("sobre");
    });
  }
  for (const evento of ["dragleave", "drop"]) {
    solta.addEventListener(evento, () => solta.classList.remove("sobre"));
  }
  solta.addEventListener("drop", (e) => {
    e.preventDefault();
    const arquivo = e.dataTransfer.files[0];
    if (arquivo) enviar(arquivo);
  });
  // Soltar fora da área também não pode navegar para fora.
  addEventListener("dragover", (e) => e.preventDefault());
  addEventListener("drop", (e) => e.preventDefault());

  $("procurar").onclick = async () => {
    const r = await pedir("/api/procurar", {});
    if (r.cancelado) return;
    $("caminho").value = r.caminho;
    abrirPorCaminho(r.caminho);
  };
  $("abrir-caminho").onclick = () => abrirPorCaminho($("caminho").value.trim());
  $("caminho").addEventListener("keydown", (e) => {
    if (e.key === "Enter") abrirPorCaminho($("caminho").value.trim());
  });
}

async function enviar(arquivo) {
  const extensao = arquivo.name.slice(arquivo.name.lastIndexOf(".")).toLowerCase();
  if (app.formatos && !app.formatos.includes(extensao)) {
    // Barrar aqui poupa subir um arquivo grande só para o servidor
    // recusar por causa da extensão.
    return falhar("erro-abrir", new Error(
      `Não sei ler "${arquivo.name}". Aceito EPUB, PDF, TXT e Markdown.`));
  }

  const dados = new FormData();
  dados.append("arquivo", arquivo);
  dados.append("ocr", $("ocr").checked ? "sempre" : "auto");
  dados.append("notas", $("notas").checked ? "true" : "false");

  ocupado(true, `Lendo ${arquivo.name}…`);
  try {
    aceitar(await pedir("/api/enviar", dados));
  } catch (erro) {
    falhar("erro-abrir", erro);
  } finally {
    ocupado(false);
  }
}

async function abrirPorCaminho(caminho) {
  if (!caminho) return;
  ocupado(true, "Lendo…");
  try {
    aceitar(await pedir("/api/abrir", {
      caminho,
      ocr: $("ocr").checked ? "sempre" : "auto",
      notas: $("notas").checked,
    }));
  } catch (erro) {
    falhar("erro-abrir", erro);
  } finally {
    ocupado(false);
  }
}

function aceitar(detalhe) {
  $("erro-abrir").hidden = true;
  // Se o livro já tinha projeto, o servidor devolve o antigo em vez de
  // criar uma cópia — com as correções de texto que já foram feitas nele.
  entrarEmPreparar(detalhe);
}

/* Vai para a tela de ajustes. Um projeto que já tem áudio ganha o atalho
 * de ouvir sem regerar — foi só reaberto, não precisa refazer nada. */
function entrarEmPreparar(detalhe) {
  app.livro = detalhe;
  desenharPreparar(detalhe);
  $("ouvir-pronto").hidden = !detalhe.pronto;
  $("progresso").hidden = true;
  $("erro-preparar").hidden = true;
  restaurarBotoes();
  mostrar("preparar");
}

async function abrirProjeto(nome) {
  try {
    const detalhe = await pedir("/api/projetos/abrir", { nome });
    if (detalhe.pronto) return abrirPlayer();
    entrarEmPreparar(detalhe);
  } catch (erro) {
    falhar("erro-abrir", erro);
  }
}

function ocupado(sim, mensagem = "") {
  const solta = $("solta");
  solta.querySelector("strong").textContent = sim ? mensagem : "Solte o arquivo aqui";
  solta.style.pointerEvents = sim ? "none" : "";
  solta.style.opacity = sim ? ".6" : "";
}

/* Um só ouvinte para a lista inteira, com a ação no `data-acao`. Ligar um
 * handler por botão obrigaria a religar tudo a cada redesenho. */
function ligarListaDeProjetos() {
  $("lista-projetos").addEventListener("click", async (e) => {
    const alvo = e.target.closest("[data-acao]");
    const item = e.target.closest(".projeto");
    if (!alvo || !item) return;
    const nome = item.dataset.nome;
    const projeto = app.projetos.find((p) => p.nome === nome);

    try {
      if (alvo.dataset.acao === "abrir") return abrirProjeto(nome);
      if (alvo.dataset.acao === "finder") return pedir("/api/revelar", { nome });

      if (alvo.dataset.acao === "limpar") {
        const ok = await confirmar(
          "Apagar o áudio?",
          `O áudio e o cache de "${projeto.titulo}" serão apagados. ` +
          "O texto já revisado fica, e você pode gerar de novo com outra voz.",
          "Apagar o áudio");
        if (!ok) return;
        await pedir("/api/projetos/apagar-audio", { nome });
      } else {
        const ok = await confirmar(
          "Apagar o projeto?",
          `"${projeto.titulo}" será apagado por inteiro — texto, áudio, ` +
          `correções e cache (${tamanho(projeto.tamanho)}). Não dá para desfazer.`,
          "Apagar tudo");
        if (!ok) return;
        await pedir("/api/projetos/apagar", { nome });
      }
      await sincronizar();
    } catch (erro) {
      falhar("erro-abrir", erro);
    }
  });
}

/* Confirmação em diálogo, não em `confirm()`: o nativo não deixa nomear o
 * botão, e "OK" para apagar um livro inteiro não diz o que vai acontecer. */
function confirmar(titulo, texto, rotulo) {
  $("confirmar-titulo").textContent = titulo;
  $("confirmar-texto").textContent = texto;
  $("confirmar-sim").textContent = rotulo;
  const dialogo = $("confirmar");
  dialogo.showModal();
  return new Promise((resolver) => {
    const fim = (resposta) => {
      dialogo.close();
      $("confirmar-sim").onclick = $("confirmar-nao").onclick = null;
      resolver(resposta);
    };
    $("confirmar-sim").onclick = () => fim(true);
    $("confirmar-nao").onclick = () => fim(false);
    dialogo.addEventListener("cancel", () => fim(false), { once: true });
  });
}

/* ============================================================= preparar */

function ligarPreparar() {
  // A caixa está dentro do <summary>, que abre o <details> ao ser
  // clicado. Sem o stopPropagation, marcar o capítulo abriria a amostra
  // junto, e a lista inteira ficaria sanfonando a cada clique.
  $("p-sumario").addEventListener("click", (e) => {
    if (e.target.type === "checkbox") e.stopPropagation();
  });
  $("p-sumario").addEventListener("change", async (e) => {
    const caixa = e.target;
    if (caixa.type !== "checkbox") return;
    try {
      await pedir("/api/trecho", { id: caixa.dataset.id, ler: caixa.checked });
      const detalhe = await pedir("/api/projetos/abrir", { nome: app.livro.nome });
      app.livro = detalhe;
      desenharPreparar(detalhe);
      // Reabre o capítulo que o usuário estava olhando, para a lista não
      // se fechar debaixo dele a cada marcação.
      const item = $("p-sumario").querySelector(`details[data-id="${caixa.dataset.id}"]`);
      if (item) item.open = true;
    } catch (erro) {
      caixa.checked = !caixa.checked;
      falhar("erro-preparar", erro);
    }
  });

  // Abrir um capítulo troca a amostra de três frases pela lista inteira,
  // editável. Carregada só ao abrir: um livro tem milhares de falas, e
  // mandar todas de uma vez deixaria lenta justamente a tela onde se
  // decide se vale gastar horas de síntese.
  $("p-sumario").addEventListener("toggle", async (e) => {
    const item = e.target;
    if (!item.open) return;
    const caixa = item.querySelector(".amostra[data-carregar]");
    if (!caixa) return;
    const id = caixa.dataset.carregar;
    delete caixa.dataset.carregar;
    caixa.innerHTML = '<p class="carregando">carregando…</p>';
    try {
      desenharFalasDoCapitulo(caixa, await pedir("/api/capitulo-falas", { id }));
    } catch (erro) {
      caixa.innerHTML = `<p class="carregando">${escapar(erro.message)}</p>`;
    }
  }, true);

  $("p-sumario").addEventListener("click", (e) => {
    const linha = e.target.closest(".fala-revisao");
    if (!linha) return;
    const f = app.revisao?.[linha.dataset.id];
    if (!f) return;
    const acao = e.target.closest("[data-acao]")?.dataset.acao;
    if (acao === "tocar") return ouvirFala(linha, f);
    // Sem botão, o clique no texto também edita: é o alvo maior.
    abrirEditor({ ...f, falado: f.texto });
  });

  $("trocar-livro").onclick = voltarParaLista;
  $("ouvir-pronto").onclick = abrirPlayer;
  $("reextrair").onclick = async () => {
    const ok = await confirmar(
      "Reextrair o texto?",
      "O arquivo original será lido de novo com a versão atual do extrator. " +
      "Correções que você fez à mão no texto serão perdidas, e o áudio " +
      "precisará ser gerado outra vez.",
      "Reextrair");
    if (!ok) return;
    try {
      entrarEmPreparar(await pedir("/api/projetos/reextrair", { nome: app.livro.nome }));
    } catch (erro) {
      falhar("erro-preparar", erro);
    }
  };
  $("gerar").onclick = gerar;
  $("cancelar").onclick = () => app.tarefa && pedir(`/api/tarefa/${app.tarefa}/cancelar`, {});
}

/* Volta para a lista. Fecha o projeto no servidor antes: é lá que o
 * estado mora, e sem fechar a próxima carga voltaria para cá. */
async function voltarParaLista() {
  som.pause();
  som.removeAttribute("src");
  await pedir("/api/fechar", {});
  await sincronizar();
}

function preencherVozes(vozes, motores) {
  if (!vozes.length) {
    $("voz").innerHTML = "<option>nenhuma voz disponível</option>";
    $("gerar").disabled = true;
    return;
  }
  // A ordem de `motores` já é a de preferência do servidor, então a
  // primeira opção da lista é a melhor voz que esta máquina tem.
  const ordenadas = [...vozes].sort(
    (a, b) => motores.indexOf(a.motor) - motores.indexOf(b.motor)
  );
  $("voz").innerHTML = ordenadas
    .map((v) => {
      const detalhes = [v.motor, v.genero, v.idioma].filter(Boolean).join(" · ");
      return `<option value="${v.motor}:${v.id}">${escapar(v.nome)} — ${escapar(detalhes)}</option>`;
    })
    .join("");
}

function desenharPreparar(livro) {
  $("p-titulo").textContent = livro.titulo;
  $("p-autor").textContent = [livro.autor, livro.origem && `de ${livro.origem}`]
    .filter(Boolean).join(" · ");
  $("p-capitulos").textContent = livro.capitulos;
  const fora = (livro.falas_no_livro || livro.falas) - livro.falas;
  $("p-falas").innerHTML = livro.falas.toLocaleString("pt-BR")
    + (fora > 0 ? ` <span class="fora-conta">de ${livro.falas_no_livro}</span>` : "");
  $("p-duracao").textContent = hms(livro.previsao.duracao_audio);
  $("p-tempo").textContent = "~" + hms(livro.previsao.tempo_de_sintese);
  $("p-tamanho").textContent = Math.round(livro.previsao.tamanho_m4b / 1e6) + " MB";

  $("p-sumario").innerHTML = livro.estrutura
    .map((c, i) => `<details class="${c.ler ? "" : "fora"}" data-id="${c.id}">
        <summary>
          <input type="checkbox" ${c.ler ? "checked" : ""} data-id="${c.id}"
                 title="Desmarque para não ler este capítulo">
          <span class="n">${i + 1}</span>
          <span>${escapar(c.titulo)}</span>
          <span class="dur">${c.ler ? `${c.falas} falas · ${hms(c.duracao)}` : "fora do áudio"}</span>
        </summary>
        <div class="amostra" data-carregar="${c.id}">${
          c.amostra.map((t) => `<p>${escapar(t)}</p>`).join("")
        }</div>
      </details>`)
    .join("");
}

/* Volta do player para a tela de ajustes — depois de corrigir uma frase,
 * ou só para trocar de voz. O cache faz a segunda geração custar apenas
 * as falas que mudaram. */
async function voltarParaPreparar() {
  som.pause();
  entrarEmPreparar(app.livro);
}

function desenharFalasDoCapitulo(caixa, falas) {
  app.revisao = app.revisao || {};
  for (const f of falas) app.revisao[f.id] = f;
  caixa.innerHTML = falas.length
    ? falas.map((f) => `<p class="fala-revisao ${f.ler ? "" : "fora"}" data-id="${f.id}">
         <span class="acoes-fala">
           <button data-acao="tocar" title="Ouvir só esta frase">▶</button>
           <button data-acao="editar" title="Reescrever ou tirar do áudio">✎</button>
         </span>${escapar(f.texto)}</p>`).join("")
    : '<p class="carregando">nada para ler neste capítulo</p>';
}

/* Toca uma frase sozinha, sintetizada na hora.
 *
 * Um <audio> só para todas as prévias: tocar uma nova interrompe a
 * anterior, que é o que se espera ao clicar em outra linha, e evita um
 * coro de frases sobrepostas. */
const previa = new Audio();

async function ouvirFala(linha, fala) {
  const botao = linha.querySelector('[data-acao="tocar"]');
  if (!previa.paused && previa.dataset.id === fala.id) {
    previa.pause();
    return marcarTocando(null);
  }
  previa.pause();
  marcarTocando(botao, "…");
  botao.disabled = true;
  try {
    // A voz da prévia é a que está escolhida na tela: ouvir numa voz e
    // gerar em outra tornaria a prévia inútil. E o resultado vai para o
    // mesmo cache da geração, então nada é sintetizado duas vezes.
    const [motor, voz] = ($("voz").value || ":").split(":");
    previa.src = `/api/fala-audio?id=${encodeURIComponent(fala.id)}`
               + `&motor=${encodeURIComponent(motor)}&voz=${encodeURIComponent(voz)}`;
    previa.dataset.id = fala.id;
    await previa.play();
    marcarTocando(botao, "❙❙");
  } catch (erro) {
    marcarTocando(null);
    falhar("erro-preparar", new Error("Não consegui sintetizar esta frase: " + erro.message));
  } finally {
    botao.disabled = false;
  }
}

function marcarTocando(botao, rotulo = "▶") {
  for (const b of document.querySelectorAll('.fala-revisao [data-acao="tocar"]')) {
    b.classList.remove("tocando");
    b.textContent = "▶";
  }
  if (botao) {
    botao.classList.add("tocando");
    botao.textContent = rotulo;
  }
}

previa.addEventListener("ended", () => marcarTocando(null));
previa.addEventListener("pause", () => marcarTocando(null));

async function gerar() {
  $("erro-preparar").hidden = true;
  $("gerar").disabled = true;
  $("cancelar").hidden = false;
  $("progresso").hidden = false;

  const [motor, voz] = $("voz").value.split(":");
  try {
    const tarefa = await pedir("/api/sintetizar", {
      motor, voz,
      velocidade: +$("velocidade-sintese").value,
      pausas: +$("pausas").value,
      formato: $("formato").value,
    });
    app.tarefa = tarefa.id;
    await acompanhar(tarefa.id);
  } catch (erro) {
    falhar("erro-preparar", erro);
    restaurarBotoes();
  }
}

/* Sonda o estado do trabalho. Sondagem, e não fluxo de eventos, porque
 * recarregar a página no meio precisa reencontrar o progresso — e um
 * fluxo perdido não se recupera. */
async function acompanhar(id) {
  for (;;) {
    const tarefa = await pedir(`/api/tarefa/${id}`);
    $("p-cheio").style.width = tarefa.progresso * 100 + "%";
    $("p-mensagem").textContent = tarefa.mensagem;
    $("p-percentual").textContent = Math.round(tarefa.progresso * 100) + "%";

    if (tarefa.situacao === "concluido") {
      // O projeto agora tem áudio; sem atualizar isto, voltar para os
      // ajustes esconderia o botão de ouvir o que acabou de ser gerado.
      if (app.livro) app.livro.pronto = true;
      return abrirPlayer();
    }
    if (tarefa.situacao === "erro") {
      falhar("erro-preparar", new Error(tarefa.erro));
      return restaurarBotoes();
    }
    if (tarefa.situacao === "cancelado") {
      $("p-mensagem").textContent = "cancelado";
      return restaurarBotoes();
    }
    await pausa(600);
  }
}

function restaurarBotoes() {
  $("gerar").disabled = false;
  $("cancelar").hidden = true;
  app.tarefa = null;
}

/* ================================================================ ouvir */

async function abrirPlayer() {
  app.texto = await pedir("/api/texto");
  mostrar("ouvir");

  $("o-titulo").textContent = app.texto.titulo;
  $("o-autor").textContent = [app.texto.autor, app.texto.voz].filter(Boolean).join(" · ");
  document.title = app.texto.titulo + " — audiolivro";

  desenharTexto(app.texto);
  desenharSumario(app.texto);
  $("o-marcas").innerHTML = app.texto.capitulos
    .filter((c) => c.inicio !== null)
    .map((c) => `<i style="left:${(c.inicio / app.texto.duracao) * 100}%"></i>`)
    .join("");

  som.src = "/audio?" + Date.now();  // evita o cache depois de re-sintetizar
  const pos = await pedir("/api/posicao");
  som.addEventListener("loadedmetadata", () => {
    if (pos.segundo > 0) som.currentTime = pos.segundo;
  }, { once: true });
  if (pos.velocidade) {
    som.playbackRate = pos.velocidade;
    $("o-velocidade").value = pos.velocidade;
  }
  atualizar();
}

function desenharTexto(livro) {
  const alvo = $("texto");
  const pedacos = [];
  for (const cap of livro.capitulos) {
    pedacos.push(`<h2 class="cap-titulo" id="${cap.id}">${escapar(cap.titulo)}</h2>`);
    for (const bloco of cap.blocos) {
      if (bloco.tipo === "titulo") continue;  // já virou o cabeçalho acima
      const spans = bloco.falas
        .map((f) => `<span class="fala${f.ler ? "" : " fora"}" data-id="${f.id}"`
                  + `${f.ler ? "" : ' title="fora do áudio"'}>${escapar(f.texto)}</span>`)
        .join(" ");
      pedacos.push(`<p class="bloco ${bloco.tipo}">${spans}</p>`);
    }
  }
  alvo.innerHTML = pedacos.join("");

  app.capitulos = livro.capitulos.map((c) => ({ titulo: c.titulo, inicio: c.inicio }));
  // `todas` inclui as excluídas, porque o diálogo de edição precisa
  // alcançá-las para poder trazê-las de volta. `falas` é só o que tem
  // tempo na trilha, que é o índice da busca do destaque.
  app.todas = [];
  for (const cap of livro.capitulos)
    for (const bloco of cap.blocos)
      for (const f of bloco.falas)
        app.todas.push({ ...f, bloco: bloco.id, el: alvo.querySelector(`[data-id="${f.id}"]`) });
  app.falas = app.todas.filter((f) => f.inicio !== null);
  app.falas.sort((a, b) => a.inicio - b.inicio);
  app.atual = -1;
}

function desenharSumario(livro) {
  $("o-sumario").innerHTML = livro.capitulos
    .map((c, i) => `<li><a data-i="${i}" class="${c.inicio === null ? "sem-audio" : ""}"`
        + `${c.inicio === null ? ' title="fora do áudio"' : ""}>`
        + `<span class="n">${i + 1}</span><span>${escapar(c.titulo)}</span></a></li>`)
    .join("");
}

function ligarOuvir() {
  $("o-sumario").onclick = (e) => {
    const a = e.target.closest("a");
    if (!a) return;
    const inicio = app.capitulos[+a.dataset.i].inicio;
    if (inicio === null) return;  // capítulo inteiro fora do áudio
    som.currentTime = inicio;
    som.play();
  };

  $("texto").addEventListener("click", (e) => {
    const span = e.target.closest(".fala");
    if (!span) return;
    const fala = app.todas.find((f) => f.id === span.dataset.id);
    if (!fala) return;
    // Clique pula para a frase; com Alt, abre a edição. Uma frase fora do
    // áudio não tem para onde pular, então o clique simples abre a edição
    // também — é a única coisa que ainda dá para fazer com ela.
    if (e.altKey || fala.inicio === null) return abrirEditor(fala);
    som.currentTime = fala.inicio;
    som.play();
  });

  $("o-tocar").onclick = () => (som.paused ? som.play() : som.pause());
  $("o-voltar15").onclick = () => (som.currentTime = Math.max(0, som.currentTime - 15));
  $("o-avancar15").onclick = () => (som.currentTime += 15);
  $("o-velocidade").onchange = (e) => { som.playbackRate = +e.target.value; guardar(); };
  $("o-revelar").onclick = () => pedir("/api/revelar", {});
  $("o-baixar").onclick = abrirExportar;
  $("ex-fechar").onclick = () => $("exportar").close();
  $("ex-baixar").onclick = exportarEBaixar;
  $("ex-formato").onchange = notaDeExportacao;
  $("ex-partes").onchange = notaDeExportacao;
  $("o-voltar").onclick = voltarParaLista;
  $("o-refazer").onclick = voltarParaPreparar;

  $("o-trilho").onclick = (e) => {
    const caixa = e.currentTarget.getBoundingClientRect();
    som.currentTime = ((e.clientX - caixa.left) / caixa.width) * (som.duration || 0);
  };

  som.addEventListener("timeupdate", atualizar);
  som.addEventListener("loadedmetadata", atualizar);
  som.addEventListener("play", () => ($("o-tocar").textContent = "❙❙ Pausar"));
  som.addEventListener("pause", () => { $("o-tocar").textContent = "▶︎ Ouvir"; guardar(); });

  // Quem rola o texto com a mão está procurando alguma coisa; continuar
  // arrastando a página atrás do áudio nesse momento é brigar com ele. A
  // perseguição volta sozinha quando a frase que soa reaparece.
  $("palco").addEventListener("wheel", () => {
    app.seguirTexto = false;
    clearTimeout(app._retomar);
    app._retomar = setTimeout(() => (app.seguirTexto = true), 6000);
  }, { passive: true });

  document.addEventListener("keydown", (e) => {
    if ($("ouvir").hidden) return;
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    const teclas = {
      " ": () => (som.paused ? som.play() : som.pause()),
      k: () => (som.paused ? som.play() : som.pause()),
      ArrowLeft: () => (som.currentTime -= 15),
      ArrowRight: () => (som.currentTime += 15),
      j: () => (som.currentTime -= 15),
      l: () => (som.currentTime += 15),
      ArrowUp: () => irPara(-1),
      ArrowDown: () => irPara(1),
    };
    if (teclas[e.key]) { e.preventDefault(); teclas[e.key](); }
  });

  ligarEditor();
  ligarBotaoDeEditar();
}

/* O botão de editar aparece ao passar o mouse sobre a frase.
 *
 * A edição era só ⌥+clique, e uma tecla modificadora que nada na tela
 * menciona é o mesmo que não existir. Agora o atalho continua, mas há
 * uma porta visível: quem passa o mouse descobre sozinho.
 *
 * Um botão só, reposicionado, em vez de um por frase — um livro tem
 * milhares delas. */
function ligarBotaoDeEditar() {
  const botao = $("editar-flutuante");
  let alvo = null;

  const esconder = () => { botao.hidden = true; alvo = null; };

  $("texto").addEventListener("mouseover", (e) => {
    const span = e.target.closest(".fala");
    if (!span || span === alvo) return;
    alvo = span;
    const caixas = span.getClientRects();
    const fim = caixas[caixas.length - 1];
    if (!fim) return esconder();
    botao.hidden = false;
    // Ancorado no fim da frase e acima dela, para não tapar o texto que
    // se está lendo nem o começo da frase seguinte.
    botao.style.left = Math.min(fim.right + 6, innerWidth - 90) + "px";
    botao.style.top = Math.max(fim.top - 26, 6) + "px";
  });

  // Sair do texto esconde, mas passar por cima do próprio botão não —
  // senão ele some justamente quando se vai clicar nele.
  $("texto").addEventListener("mouseleave", (e) => {
    if (e.relatedTarget !== botao) esconder();
  });
  botao.addEventListener("mouseleave", esconder);
  $("palco").addEventListener("scroll", esconder, { passive: true });

  botao.onclick = () => {
    if (!alvo) return;
    const fala = app.todas.find((f) => f.id === alvo.dataset.id);
    esconder();
    if (fala) abrirEditor(fala);
  };
}

function indiceEm(t) {
  let lo = 0, hi = app.falas.length - 1, achado = 0;
  while (lo <= hi) {
    const meio = (lo + hi) >> 1;
    if (app.falas[meio].inicio <= t) { achado = meio; lo = meio + 1; } else hi = meio - 1;
  }
  return achado;
}

function atualizar() {
  if (!app.falas.length) return;
  const t = som.currentTime;
  const total = som.duration || app.texto?.duracao || 1;
  $("o-decorrido").style.width = (t / total) * 100 + "%";
  $("o-tempo").textContent = `${hms(t)} / ${hms(total)}`;

  const i = indiceEm(t);
  if (i !== app.atual && app.falas[i]) {
    app.falas[app.atual]?.el?.classList.remove("soando");
    app.falas[i].el?.classList.add("soando");
    app.atual = i;
    if (app.seguirTexto && !som.paused) rolarAte(app.falas[i].el);
  }

  // Capítulo sem áudio tem `inicio` nulo, e em JavaScript `null <= 0` é
  // verdadeiro: numa comparação ingênua ele passaria por já ter começado,
  // e o rodapé anunciaria o índice remissivo no segundo zero do livro.
  let c = -1;
  for (let k = 0; k < app.capitulos.length; k++) {
    const ini = app.capitulos[k].inicio;
    if (ini !== null && ini <= t) c = k;
  }
  if (c < 0) c = app.capitulos.findIndex((x) => x.inicio !== null);
  if (c !== app.capAtual) {
    app.capAtual = c;
    $("o-capitulo").textContent = app.capitulos[c]?.titulo || "";
    document.querySelectorAll("#o-sumario a").forEach((a, k) =>
      a.classList.toggle("atual", k === c));
  }
}

function rolarAte(el) {
  if (!el) return;
  const palco = $("palco");
  const caixa = el.getBoundingClientRect();
  const limite = palco.getBoundingClientRect();
  // Só rola quando a frase saiu do terço confortável da tela. Rolar a
  // cada frase deixa o texto em movimento perpétuo e faz perder a linha.
  if (caixa.top < limite.top + 80 || caixa.bottom > limite.bottom - 160)
    palco.scrollBy({ top: caixa.top - limite.top - limite.height * 0.34, behavior: "smooth" });
}

function irPara(passo) {
  const i = Math.min(Math.max(app.atual + passo, 0), app.falas.length - 1);
  som.currentTime = app.falas[i].inicio;
}

/* ----------------------------------------------------------- exportar */

function abrirExportar() {
  som.pause();
  $("ex-progresso").hidden = true;
  notaDeExportacao();
  $("exportar").showModal();
}

function notaDeExportacao() {
  const formato = $("ex-formato").value;
  const partes = $("ex-partes").value === "1";
  const dur = app.texto?.duracao || 0;
  // WAV é PCM de 16 bits a 22 kHz mono: ~44 kB por segundo, contra ~8 kB
  // dos formatos comprimidos. Dizer o tamanho antes evita a surpresa de
  // um download de 1,5 GB.
  const porSegundo = formato === "wav" ? 44100 : 8000;
  const mb = Math.max(1, Math.round((dur * porSegundo) / 1e6));
  const avisos = [`Aproximadamente ${mb} MB.`];
  if (formato === "mp3" && !partes)
    avisos.push("MP3 não guarda capítulos; para navegá-los, use M4B ou separe por capítulo.");
  if (formato === "wav") avisos.push("WAV não tem perda, mas é grande demais para enviar por mensagem.");
  if (partes) avisos.push("Cada capítulo vira um arquivo numerado, com título e autor, tudo num .zip.");
  $("ex-nota").textContent = avisos.join(" ");
}

async function exportarEBaixar() {
  $("ex-baixar").disabled = true;
  $("ex-progresso").hidden = false;
  try {
    const tarefa = await pedir("/api/exportar", {
      formato: $("ex-formato").value,
      por_capitulo: $("ex-partes").value === "1",
    });
    for (;;) {
      const s = await pedir(`/api/tarefa/${tarefa.id}`);
      $("ex-cheio").style.width = s.progresso * 100 + "%";
      $("ex-mensagem").textContent = s.mensagem;
      $("ex-pct").textContent = Math.round(s.progresso * 100) + "%";
      if (s.situacao === "concluido") {
        // Um <a download> clicado por script é o único jeito de o
        // navegador salvar o arquivo sem sair da página.
        const a = document.createElement("a");
        a.href = "/api/baixar?arquivo=" + encodeURIComponent(s.resultado.arquivo);
        a.download = s.resultado.arquivo;
        document.body.appendChild(a); a.click(); a.remove();
        $("ex-mensagem").textContent = `${s.resultado.arquivo} · ${tamanho(s.resultado.bytes)}`;
        break;
      }
      if (s.situacao === "erro") { $("ex-mensagem").textContent = s.erro; break; }
      if (s.situacao === "cancelado") break;
      await pausa(500);
    }
  } catch (erro) {
    $("ex-mensagem").textContent = erro.message;
  } finally {
    $("ex-baixar").disabled = false;
  }
}

/* ------------------------------------------------------- corrigir texto */

let emEdicao = null;

function ligarEditor() {
  $("editor-fechar").onclick = () => $("editor").close();

  // Excluir e reincluir são o mesmo botão, com o rótulo trocado: são a
  // mesma decisão vista dos dois lados, e separar em dois botões faria um
  // deles estar sempre desabilitado.
  $("editor-pular").onclick = () => alternarLeitura(emEdicao.id, !emEdicao.ler);
  $("editor-pular-bloco").onclick = () => alternarLeitura(emEdicao.bloco, !emEdicao.ler, true);

  $("editor-salvar").onclick = async () => {
    const texto = $("editor-texto").value.trim();
    if (!texto || !emEdicao) return;
    try {
      await pedir("/api/fala", { id: emEdicao.id, texto });
      emEdicao.falado = texto;
      if (app.revisao?.[emEdicao.id]) app.revisao[emEdicao.id].texto = texto;
      for (const el of document.querySelectorAll(`[data-id="${emEdicao.id}"]`)) {
        el.classList.add("corrigida");
        // Na conferência o que se vê é o texto falado, então ele precisa
        // refletir a correção na hora; no player o que se vê é o texto
        // original do livro, que não muda.
        if (el.classList.contains("fala-revisao")) el.textContent = texto;
      }
      $("editor").close();
      marcarPendencia();
    } catch (erro) {
      alert(erro.message);
    }
  };
}

function abrirEditor(fala) {
  $("editar-flutuante").hidden = true;
  emEdicao = fala;
  $("editor-texto").value = fala.falado;
  $("editor-pular").textContent = fala.ler ? "Não ler esta frase" : "Voltar a ler";
  $("editor-pular-bloco").textContent = fala.ler
    ? "Não ler o parágrafo" : "Voltar a ler o parágrafo";
  $("editor").showModal();
}

/* Tira (ou devolve) um trecho do áudio. `bloco` decide se o alvo é a
 * frase ou o parágrafo inteiro, que é o que se quer na maior parte das
 * vezes: o que sobra de uma extração ruim vem em parágrafo, não em frase. */
async function alternarLeitura(id, ler, bloco = false) {
  try {
    await pedir(bloco ? "/api/trecho" : "/api/fala", { id, ler });
    // O mesmo diálogo serve ao player e à tela de conferência, que
    // desenham a mesma fala em elementos diferentes. Em vez de manter
    // duas listas em memória, marcamos pelo id no DOM: o que estiver na
    // tela é atualizado, qualquer que seja a tela.
    const ids = bloco
      ? Object.values(app.revisao || {}).filter((f) => f.bloco === id).map((f) => f.id)
        .concat((app.todas || []).filter((f) => f.bloco === id).map((f) => f.id))
      : [id];
    for (const alvo of new Set(ids)) {
      for (const el of document.querySelectorAll(`[data-id="${alvo}"]`))
        el.classList.toggle("fora", !ler);
      if (app.revisao?.[alvo]) app.revisao[alvo].ler = ler;
      const naTrilha = (app.todas || []).find((f) => f.id === alvo);
      if (naTrilha) naTrilha.ler = ler;
    }
    $("editor").close();
    marcarPendencia();
  } catch (erro) {
    alert(erro.message);
  }
}

/* Mudança no texto só vira som depois de refazer. Sem oferecer o botão,
 * o usuário edita, não ouve diferença nenhuma e conclui que não funcionou. */
function marcarPendencia() {
  app.pendentes = (app.pendentes || 0) + 1;
  // O botão de refazer só faz sentido no player: quem está na tela de
  // conferência ainda vai clicar em "Gerar" de qualquer jeito.
  if ($("ouvir").hidden) return;
  const botao = $("o-refazer");
  botao.hidden = false;
  botao.textContent = `Refazer o áudio (${app.pendentes} ${
    app.pendentes === 1 ? "mudança" : "mudanças"})`;
}

/* ------------------------------------------------------------ marcador */

let ultimoGuardado = 0;
function guardar() {
  if ($("ouvir").hidden) return;
  const agora = Date.now();
  if (agora - ultimoGuardado < 2000) return;
  ultimoGuardado = agora;
  navigator.sendBeacon?.("/api/posicao", new Blob(
    [JSON.stringify({ segundo: som.currentTime, velocidade: som.playbackRate })],
    { type: "application/json" }));
}
setInterval(() => { if (!som.paused) guardar(); }, 5000);
addEventListener("beforeunload", () => { ultimoGuardado = 0; guardar(); });

/* --------------------------------------------------------- utilidades */

async function pedir(url, corpo) {
  const opcoes = corpo === undefined
    ? {}
    : corpo instanceof FormData
      ? { method: "POST", body: corpo }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };

  const resposta = await fetch(url, opcoes);
  if (!resposta.ok) {
    // O FastAPI põe a mensagem em `detail`; sem ela, o status é tudo que
    // temos, e mostrar "[object Object]" seria pior que o número.
    let detalhe = `Erro ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (typeof corpo.detail === "string") detalhe = corpo.detail;
    } catch { /* resposta sem JSON */ }
    throw new Error(detalhe);
  }
  return resposta.json();
}

function falhar(id, erro) {
  const caixa = $(id);
  caixa.textContent = erro.message || String(erro);
  caixa.hidden = false;
}

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

function hms(s) {
  if (!isFinite(s) || s < 0) return "0:00";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), g = Math.floor(s % 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}:${String(g).padStart(2, "0")}`;
}

function tamanho(bytes) {
  if (!bytes) return "";
  if (bytes < 1e6) return Math.round(bytes / 1e3) + " KB";
  if (bytes < 1e9) return Math.round(bytes / 1e6) + " MB";
  return (bytes / 1e9).toFixed(1).replace(".", ",") + " GB";
}

function escapar(t) {
  return String(t ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
