# Quem é dono de cada dado — Studio ou Excel

Definido pelo dono em 17/09/2026. Uma aba tem UM dono: o lugar onde o dado é
digitado. O outro lado, quando existe, é consulta.

## Passa para o Studio

| O quê | Situação |
|---|---|
| Custo fixo | Digitado no Studio. O Excel vira consulta |
| Salários / folha | Digitado no Studio |
| Não operacionais | Digitado no Studio |
| Cheques | Preenchimento e baixa passam para o Studio |
| Devoluções | Passa para o Studio |

## Continua no Excel

| Aba | Por quê |
|---|---|
| SAIDAS PIX-BOLETO 2026 | O extrato traz gastos que já entram como custo fixo; jogar direto contabilizaria duas vezes |
| CARTÕES | O que é debitado ali precisa ser analisado e realocado — mercadoria, ADS, custo fixo (Hostgator) |
| ADS E CROSS | Nem tudo ali é ADS: tem transporte até o Full, taxa de página ativa, selo de loja oficial (R$ 99) |
| SIMPLES - FLEX | Simples cai no extrato; Flex é pago por DDA |
| AJUSTE DE PLANILHA | É o preparo da base antes de virar BASE DE VENDAS |
| PREÇO DE CUSTO | Renan consolida SKU ali. **Não deve ser considerado pelo Studio** |
| BASE DE VENDAS 2026 | A base fica no Excel; o Studio lê para os indicadores |
| MINHAS DINÂMICAS / DINÂMICA | Ficam no Excel; o Studio mostra algumas |

## Depende de coisa que ainda não existe

| O quê | O que falta |
|---|---|
| A RECEBER | Integração com as plataformas. Dinheiro libera e provisiona a cada venda — sem integração, nenhum número fica atualizado |
| DASH | O Studio mostra, quando o resto estiver rodando |
| FATURAMENTO CONSOLIDADO | Indicadores mais para frente |

---

## A decisão que ficou de pé

**Custo fixo passa para o Studio, e o mesmo gasto aparece no extrato.** São
duas fontes para o mesmo número, e a dupla contagem é questão de tempo. Os
dois caminhos possíveis:

| Caminho | Como fica |
|---|---|
| **A** — o Studio manda no custo fixo | O extrato continua sendo conferência; ao lançar a SAIDAS PIX-BOLETO, as linhas que já são custo fixo ficam de fora. Exige a exclusão manual que ele já faz hoje |
| **B** — o extrato manda em tudo | Se está no extrato, contabiliza; se não está, não contabiliza. Acaba a exclusão manual e acaba a dupla fonte — mas o custo fixo deixa de ser previsto e passa a ser histórico: só aparece depois de pago |

Sem escolher uma, as duas fontes vão discordar, e a discordância aparece como
erro de indicador meses depois.
