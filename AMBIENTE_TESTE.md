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

## Passo 1 — Copiar a planilha (5 min)

1. Abra a planilha **MartinSousa - Financeiro**
2. `Arquivo → Fazer uma cópia`
3. Nome: **`MartinSousa - Financeiro (TESTE)`**
4. Na cópia: `Compartilhar` → adicione o **mesmo e-mail de serviço** que a
   planilha original já tem, como **Editor**

> Para descobrir o e-mail de serviço: abra a planilha original em
> `Compartilhar` e copie o endereço terminado em
> `.iam.gserviceaccount.com`.

## Passo 2 — Criar a pasta no Drive (2 min)

1. No Drive, crie a pasta **`MS Studio - Imagens (TESTE)`**
2. Compartilhe com o mesmo e-mail de serviço, como **Editor**
3. Abra a pasta e copie o **ID** da barra de endereço:
   `drive.google.com/drive/folders/`**`ISTO_AQUI`**

## Passo 3 — Criar o serviço no Railway (10 min)

1. No projeto do Railway: `New` → `GitHub Repo` → o mesmo repositório
2. Em `Settings → Source`, mude a branch para **`homologacao`**
3. Em `Settings → Networking`, clique em **`Generate Domain`**
   (o Railway cria um endereço sozinho, sem mexer em DNS)
4. Em `Variables`, copie **todas** as variáveis do serviço de produção

## Passo 4 — Trocar três coisas nos secrets do teste (3 min)

No `STREAMLIT_SECRETS` do serviço de teste, **acrescente estas duas linhas
no topo** do arquivo:

```toml
AMBIENTE = "homologacao"
PLANILHA_NOME = "MartinSousa - Financeiro (TESTE)"
```

E **troque** o valor da pasta do Drive pelo ID do Passo 2:

```toml
DRIVE_PASTA_IMAGENS_ID = "id_da_pasta_de_teste"
```

Pronto. O resto fica igual.

---

## Como saber que deu certo

Ao abrir o endereço de teste, deve aparecer uma **faixa amarela** no topo:

> 🧪 AMBIENTE DE TESTE — planilha "MartinSousa - Financeiro (TESTE)" ·
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
