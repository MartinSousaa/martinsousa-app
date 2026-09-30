# ACHADOS ABERTOS — o que foi mapeado e ainda NÃO foi corrigido

Este arquivo é lido por `checar_alcance.py`, e **reprova a conferência**
enquanto houver item aberto sem motivo escrito.

## POR QUE ELE EXISTE

30/09. Varri a cadeia Studio → Gemini, achei treze defeitos, escrevi todos
numa lista minha, corrigi onze e **deixei dois**. Um deles — `_tem_fotos`
decidindo o texto do prompt pela chave da OpenAI — é uma das causas de
"produto nada a ver com o original", e ficou aberto por horas enquanto eu
relatava "APROVADO".

O dono perguntou: *"como me garante que não há outros erros que mapeou e não
tratou?"*. A resposta honesta é que eu não garanto por promessa. Os oito
verificadores guardam o CÓDIGO; nada guardava a minha LISTA. Achado anotado
num bilhete depende de eu lembrar — e à mão eu não faço igual duas vezes.

Então a lista deixa de ser bilhete e passa a ser trava, igual ao que esta
base já faz com as isenções (`MUDAS_POR_ESCOLHA`, `THREADS_SEM_TELA`): ou o
item é corrigido e sai daqui, ou fica com MOTIVO escrito de por que não foi.

## COMO USAR

Item aberto tem três linhas obrigatórias:

    ### <título curto>
    ONDE: arquivo:linha
    POR QUE AINDA NÃO: <motivo, com todas as letras>

Sem a linha `POR QUE AINDA NÃO`, a conferência reprova. "Esqueci" não é
motivo — mas é uma resposta honesta, e escrita ela para de ser esquecimento.

## ABERTOS

### Por que as oito peças do «Compasso Cortador Colorido» saíram erradas
ONDE: toda a cadeia · evidência em `log_imagem.py` (contexto do log)
POR QUE AINDA NÃO: a análise do dia 30/09 foi feita em cima do `.txt` do
histórico que o dono baixou, e aquele arquivo **misturava as rodadas de duas
pessoas** — o contexto do log era um global de processo, então o histórico de
um produto veio com peças de outro dentro, carimbadas com o nome de quem não
as gerou. O global foi corrigido (contexto por thread, com herança na criação
da thread), mas o log ANTIGO não se conserta: as linhas já gravadas continuam
com produto e usuário errados. A pergunta original — por que as peças dele
saíram com moldura, texto cortado e produto fora de escala — precisa ser
refeita com um histórico novo, gerado depois desta correção. Dito em voz alta
em vez de escondido: **eu afirmei que o plano estava misturado entre dois
produtos, e essa afirmação não se sustenta.** Ela saiu do log corrompido.

### A trava do plano misturado ficou pronta e foi retirada
ONDE: imagem.py:576 (`plano_misturado`) e o painel de confirmação
POR QUE AINDA NÃO: a função fica, e o aviso também — com um plano coerente ela
devolve `""` e não custa nada. O que saiu foi a TRAVA do botão Confirmar:
trancar a geração com base num defeito que eu não consigo mais provar é alarme
falso, e alarme falso ensina a desviar do alarme verdadeiro junto. A trava
volta no dia em que um plano real vier misturado.


### O `dall-e-3` é encontrado, mas o Studio não sabe FALAR com ele
ONDE: imagem.py:_chamar_openai_geracao
POR QUE AINDA NÃO: o filtro de modelos foi corrigido e a conta que só tem
`dall-e-*` deixa de ficar sem motor — mas as três tentativas do caminho da
OpenAI usam a Responses API com `tools=[image_generation]`, e o `dall-e-3`
não atende por ali nem aceita foto de referência. Com fotos, ele falharia nas
três e cairia no Gemini do mesmo jeito. Fazer o `dall-e-3` funcionar de
verdade é escrever uma quarta chamada (`images.generate` com as fotos fora),
e isso é construção, não conserto de filtro. O que mudou hoje: a tela de
Diagnóstico das APIs passa a MOSTRAR o que a conta tem, e o motor que fez
cada peça já aparece no diagnóstico dela.

### As 65 regras do prompt só são medidas com o cadastro CHEIO
ONDE: checar_prompts.py:_DADOS
POR QUE AINDA NÃO: hoje só o tipo 5 é conferido com o cadastro vazio, porque
foi onde a contradição aparecia (manda fazer cota e proíbe escrever cota).
Rodar as 65 regras uma segunda vez, com cadastro vazio, dobra o tempo do
verificador — que já é a parte mais lenta do protocolo. O risco de deixar
assim está declarado: uma regra que só faz sentido com dado preenchido pode
estar quebrada no vazio sem ninguém ver.

### A régua não vê a FORMA do produto, só a cor
ONDE: medir_imagem.py:produto_diferente
POR QUE AINDA NÃO: a comparação com as fotos passou a existir em 30/09 e pega
o defeito mais relatado — o produto repintado, a cor trocada, o objeto
substituído por outro de cor diferente. O que ela NÃO vê é forma: produto da
cor certa e formato errado passa. Responder forma exige visão, e visão custa
uma chamada paga por peça — oito por geração. Medida barata que pega o caso
comum vale mais que medida cara que ninguém liga; quando o dono quiser pagar
por isso, a porta já existe (`_descrever_produto_via_claude`).

### `_processar` duplicado em placar.py e placar_core.py
ONDE: placar.py, placar_core.py
POR QUE AINDA NÃO: unificar é mudança grande e o risco tem de ser mapeado
antes. Já discordaram em 330 pontos no mesmo mês. Aberto desde 28/09.

### Corte de texto nas peças 4 e 5
ONDE: imagem.py, prompt dos tipos 4 e 5
POR QUE AINDA NÃO: preciso do prompt real de uma peça que cortou para separar
"o layout não cabe" de "o modelo desobedeceu". Sem isso eu estaria chutando.
Aberto desde 28/09.
