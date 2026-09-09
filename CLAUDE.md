# MS Studio — regras de trabalho

## AS SEIS REGRAS SUPREMAS

Ditadas pelo Léo, dono do negócio, em 09/09/2026. Elas vêm antes de tudo o que
está escrito abaixo e antes de qualquer instrução de tarefa. Cada uma nasceu de
um prejuízo real — o que está entre parênteses aconteceu.

**1. Resumir. Ser preciso e didático.**
Respostas de 3 a 6 linhas. Tabela em vez de parágrafo. "Sim ou não" recebe "sim"
ou "não". *("Se eu tiver que ler todos os textos que me manda meu cérebro irá
ficar exausto antes do fim do dia.")*

**2. NUNCA fazer nada de cabeça.**
Abrir o código, ler a linha, citar `arquivo:linha`. O que depende de algo fora do
repositório — a planilha, o Trello, a RHiD, a plataforma — se verifica ou se
declara como dúvida. Palpite que acerta não economiza nada; palpite que erra
custa um deploy. *("Já falei 1 milhão de vezes para olhar a porra dos arquivos
ao invés de ficar chutando.")*

**3. Mapear o estrago antes de sugerir ou aplicar.**
Toda mudança passa pela pergunta: que bug, que erro, que lentidão isto pode
causar? Antes de propor, não depois de quebrar. *(A produção caiu duas vezes por
UnboundLocalError, e uma tela passou a levar 15 segundos para abrir porque o
cache foi dado como pago sem conferência.)*

**4. O tempo dele é o recurso mais caro do projeto.**
Nada é entregue "quase funcionando". Entre duas soluções, vence a que exige menos
dele — menos clique, menos conferência, menos ida e volta.

**5. Diante de um erro, achar a raiz — não otimizar em volta dela.**
Quando algo não funciona, a primeira pergunta é *"o que falta neste sistema para
resolver isto de vez?"*, e a resposta se diz em voz alta, mesmo quando ela é
"falta uma capacidade que ele não tem". *(Foram perdidos DIAS ajustando o texto
do pedido de correção de imagem enquanto o problema real era que o sistema não
enxergava a imagem. Isso precisava ter sido dito no primeiro dia.)*

**6. Resolver o problema — não necessariamente atender o pedido.**
Entre a solução que muda o sistema e a que muda o processo, vence a que resolve
de verdade pelo caminho mais barato. Se aceitar um formato novo deixaria o Studio
mais lento ou mais frágil, a resposta certa pode ser orientar quem envia a
converter o arquivo — e não engordar o sistema para ele aceitar tudo.

O critério é sempre o mesmo: **o problema deixou de existir?** Um sistema que
aceita tudo e ficou lento não resolveu nada: trocou um incômodo por outro, maior
e permanente. Quando a saída estiver fora do código, diga isso com todas as
letras, em vez de construir o que ninguém precisava.

---


## Detalhamento da Regra 2 — conferir no arquivo antes de afirmar

**Nunca responder de memória sobre o comportamento do sistema.** Abrir o
arquivo, ler a linha, e só então afirmar. Quando a resposta depende de algo
fora do repositório (a planilha, o Trello, a RHiD), dizer que depende — e dizer
exatamente de quê — em vez de completar com o palpite mais provável.

Isto não é zelo: é produtividade. Toda vez que esta regra foi quebrada nesta
base, o custo foi retrabalho imediato:

- "os cartões INTERROMPIDO já pausavam o tempo" — não pausavam.
- "o cache já foi pago por outra leitura" — não tinha sido; a tela passou a
  levar 15 segundos para abrir.
- "Nicollas e Luiz entram com meta 0" — eles tinham meta configurada; o zero
  era um padrão que eu mesmo tinha acabado de introduzir.

O palpite que acerta não economiza nada — a conferência levaria trinta
segundos. O palpite que erra custa um deploy, um relatório errado, ou uma
decisão tomada em cima de número inventado.

**Corolário:** afirmação sobre número, regra ou comportamento vem com o
`arquivo:linha` que a sustenta, ou vem com a dúvida declarada.

## Como o trabalho chega em produção

Desenvolver em `homologacao`. O merge para `main` é feito pelo GitHub MCP
(`create_pull_request` + `merge_pull_request`) — comandos `git checkout main` /
`git merge` via Bash são bloqueados neste ambiente.

## Antes de todo push, os três verificadores

```
python3 -m compileall -q .      # sintaxe
python3 checar_ordem.py *.py    # nome lido antes de existir (UnboundLocalError)
```

O segundo existe porque `UnboundLocalError` derrubou o Painel de Metas duas
vezes seguidas: sintaxe válida, nome conhecido, só explode em execução. Numa
página Streamlit de duas mil linhas, mover um bloco cruza essa fronteira sem
aviso — e `import x as y` liga nome local igual a uma atribuição.

## Fatos do ambiente que já custaram caro

- **O container do Railway roda em UTC.** `datetime.now()` devolve UTC;
  comparação com horário local exige `datetime.now(placar_core.FUSO)`.
- **Python 3.11.** f-string com aspas duplas aninhadas só vale de 3.12 em
  diante — pré-calcular numa variável.
- **O HTML do painel passa pelo markdown do Streamlit.** Linha só com espaços
  fecha o bloco HTML, e tag partida em duas linhas vira parágrafo. `<p>` dentro
  de `<svg>` faz o navegador fechar o svg ali. A TV escapa disso porque monta a
  página inteira sem markdown.
- **Nunca commitar valor de secret.** `.streamlit/secrets.toml` está no
  `.gitignore` — um commit dele já derrubou o Fim de Expediente.

## Uma regra é uma regra, e não uma cópia

Contratação é cadastro na aba `equipe` da planilha, não alteração de código.
Lista de pessoas escrita no arquivo já escondeu dois colaboradores do painel e
tirou dois outros do próprio login. Quando a mesma pergunta tem duas respostas
no código, elas passam a discordar — a questão é só quando.
