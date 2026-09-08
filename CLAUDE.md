# MS Studio — regras de trabalho

## REGRA Nº 1 — Conferir no arquivo antes de afirmar

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
