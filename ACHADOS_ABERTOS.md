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

### Nenhum verificador olha a imagem que o Gemini devolve
ONDE: toda a cadeia
POR QUE AINDA NÃO: é construção nova, não correção — precisaria medir a peça
gerada (tamanho do produto no quadro, moldura, texto cortado) e reprovar
sozinha. O dono foi avisado três vezes de que este buraco existe, e a decisão
de construir é dele.

### `_processar` duplicado em placar.py e placar_core.py
ONDE: placar.py, placar_core.py
POR QUE AINDA NÃO: unificar é mudança grande e o risco tem de ser mapeado
antes. Já discordaram em 330 pontos no mesmo mês. Aberto desde 28/09.

### Corte de texto nas peças 4 e 5
ONDE: imagem.py, prompt dos tipos 4 e 5
POR QUE AINDA NÃO: preciso do prompt real de uma peça que cortou para separar
"o layout não cabe" de "o modelo desobedeceu". Sem isso eu estaria chutando.
Aberto desde 28/09.
