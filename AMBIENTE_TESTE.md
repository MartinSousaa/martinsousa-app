# Ambiente de teste (homologação)

Um segundo Studio, igual ao de verdade, onde dá para testar sem derrubar
ninguém. O código é o mesmo — o que muda são **três secrets**.

## O que é separado e o que é compartilhado

| | teste usa | por quê |
|---|---|---|
| Planilha Google | **cópia** | é onde o Studio escreve |
| Pasta do Drive | **cópia** | é onde as imagens são salvas |
| Trello | **o real** | o Studio só lê o board, nunca escreve |
| Relógio RHiD | **o real** | o Studio só lê as batidas |
| Chaves de IA | você decide | ver "Custos" no fim |

Trello e RHiD serem só leitura é o que torna isto barato: o teste roda com
os dados de verdade, sem risco.

---

## Passo 1 — Planilha de teste (FEITO)

Planilha **`MartinSousa - Financeiro - Área de Testes`**, já criada e já
compartilhada com a conta do robô.

## Passo 2 — Pasta do Drive (FEITO)

Pasta **`IMAGENS GEMINI`** de teste, ID:

```
101h6k5o125pLca2g9blxlgqRIwjCjvSZ
```

## Passo 3 — Criar o serviço no Railway (10 min)

1. No projeto do Railway: `New` → `GitHub Repo` → o mesmo repositório
2. Em `Settings → Source`, mude a branch para **`homologacao`**
3. Em `Settings → Networking`, clique em **`Generate Domain`**
   (o Railway cria um endereço sozinho, sem mexer em DNS)
4. Em `Variables`, copie **todas** as variáveis do serviço de produção

## Passo 4 — Trocar tres coisas nos secrets do teste (3 min)

No `STREAMLIT_SECRETS` do servico de teste, **acrescente estas tres linhas no
topo** do arquivo (antes de qualquer `[secao]`):

```toml
AMBIENTE = "homologacao"
PLANILHA_NOME = "MartinSousa - Financeiro - Área de Testes"
DRIVE_PASTA_IMAGENS_ID = "101h6k5o125pLca2g9blxlgqRIwjCjvSZ"
```

Se `DRIVE_PASTA_IMAGENS_ID` ja existir mais abaixo no arquivo, **apague a linha
antiga** — senao vale a de baixo e o teste salva na pasta de producao.

Atencao: cole em `Variables` do **servico** de teste, nao do **projeto**.
Variavel de projeto e herdada por todos os servicos e iria contaminar a
producao.

Pronto. O resto fica igual.

---

## Como saber que deu certo

Ao abrir o endereço de teste, deve aparecer uma **faixa amarela** no topo:

> 🧪 AMBIENTE DE TESTE — planilha "MartinSousa - Financeiro - Área de Testes" ·
> nada aqui afeta o Studio de verdade

**Se a faixa não aparecer, pare.** Sem ela, o app está escrevendo na
planilha de verdade. Quase sempre é o `AMBIENTE = "homologacao"` que ficou
faltando ou está escrito diferente.

## O dia a dia

```
homologacao  →  eu subo aqui, você testa
    ↓ (quando aprovar, e o Studio estiver vazio)
main         →  vai para app.martinsousa.com.br
```

## Custos

- **Railway**: um segundo serviço rodando.
- **Chaves de IA**: se o teste usar as mesmas chaves, gerar imagem no teste
  **gasta crédito de verdade**. Para evitar, apague as linhas
  `ANTHROPIC_API_KEY` e `GEMINI_API_KEY` dos secrets do teste — a geração
  de imagem passa a mostrar erro, e o resto do Studio funciona normal.

## Manutenção

A planilha de teste **envelhece**: metas, equipe e colunas que você mudar em
produção não aparecem no teste. Quando incomodar, refaça o Passo 1.

## Se algo der errado

O ambiente de teste não tem como quebrar a produção — são planilhas e pastas
diferentes, e o Trello e a RHiD são só leitura. Na pior das hipóteses o teste
fica fora do ar, e o Studio segue funcionando.
