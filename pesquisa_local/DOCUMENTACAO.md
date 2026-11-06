# Pesquisa local — Documentação (Alexandre Silva, 29382)

> Este ficheiro explica a tua parte do trabalho para a conseguires perceber, apresentar e defender. Tem 10 secções: começa pelo resumo em 30 segundos e termina nas perguntas prováveis da defesa.

---

## 1. Resumo em 30 segundos

"A minha parte é a **pesquisa local**. Recebo a solução do Greedy, ou seja, uma rota por veículo e por dia, e tento melhorá-la com **Hill-Climbing**.

Represento cada rota como uma **sequência de visitas** (recolhas, idas ao armazém, entregas). Gero **vizinhos** com três movimentos: **trocar**, **mover** e **inverter** visitas. Cada vizinho passa pelo **verificador do `model.py`**, e só fico com os que respeitam todas as regras e têm menos km. Repito até nenhum vizinho melhorar, que é um **ótimo local**.

- **No tiny,** chego ao ótimo do A*, 601,97 km.
- **No small,** tiro até 60 km às soluções fracas do Greedy, mas fico preso num ótimo local a 1,08 km do ótimo.
- **Com um 4.º movimento, *mover bloco*,** chego ao ótimo em 10 de 10 tentativas.

As curvas de custo × iteração mostram tudo isto."

---

## 2. Onde encaixa no trabalho do grupo

```
Fábio (pesquisa informada) ──► Greedy: rotas iniciais ──► ALEXANDRE: Hill-Climbing ──► rotas melhores ──► André (integração)
                                                              ▲
                                       model.py (verificar_viabilidade) aprova cada vizinho
```

- **O que recebes:** para cada (veículo, dia), a lista de ações no formato do `verificar_viabilidade`: `("pickup", item)`, `("warehouse", armazém)`, `("load", item)`, `("delivery", item)`. Também recebes os itens a recolher e a entregar nesse dia e a hora de partida.
- **O que devolves:** as mesmas rotas, melhoradas, e o histórico de custo por iteração, para os gráficos.
- **O que usas do grupo:** o `model.py` do Fábio, ou seja, o `Problem` e o `verificar_viabilidade`. Não alteras nada nele.
- **Solução inicial, para já:** como o `pesquisa.py` final do Fábio ainda não existe, o notebook usa o Greedy da pasta `pesquisa_informada/`, um protótipo. Quando o do Fábio estiver pronto, muda-se só a função `solucao_greedy()` no notebook.

---

## 3. Conceitos que tens de saber explicar

**Pesquisa local:** parte de uma solução completa e tenta melhorá-la com pequenas alterações. Não constrói a solução passo a passo, como o A*. Gasta pouca memória (só guarda a solução atual), mas não garante o ótimo.

**Vizinhança:** o conjunto de soluções que se obtêm com uma pequena alteração (um "movimento") à solução atual.

**Hill-Climbing ("subir a colina"):** passa sempre para um vizinho melhor e para quando não há nenhum. Neste problema "melhor" quer dizer menos km, por isso, na prática, estamos a descer.

**Ótimo local:** uma solução sem nenhum vizinho melhor, mas que não é necessariamente a melhor de todas (o ótimo global). É o grande defeito do Hill-Climbing.

**Duas estratégias:**

- **Melhor vizinho** (*steepest ascent*): avalia todos os vizinhos e escolhe o melhor. Dá passos maiores, mas cada iteração é mais cara.

- **Primeira melhoria** (*first improvement*): percorre os vizinhos por ordem aleatória e aceita o primeiro que melhora. Faz mais iterações, mas cada uma é mais barata.

**Simulated Annealing (extra):** é como o Hill-Climbing, mas às vezes aceita vizinhos piores, com probabilidade `exp(−Δ/T)`. A "temperatura" T desce com o tempo: no início aceita muitas pioras, no fim quase nenhuma. Serve para escapar a ótimos locais.

---

## 4. Como está implementado (`local.py`)

### 4.1 Representação: sequência de visitas

Uma rota é uma lista de objetos `Visita(tipo, local, itens)`:

| Símbolo | Tipo | Significado |
|---|---|---|
| `R3` | recolha | ir ao produtor 3 e recolher os itens indicados (10 min) |
| `A(5)` | armazém | descarregar o que vem a bordo (15 min) e carregar 5 itens (15 min) |
| `A` | armazém | só descarregar, ou o regresso final |
| `E9` | entrega | ir ao cliente 9 e entregar os itens indicados (10 min) |

Exemplo real (tiny, veículo 1, dia 30): `R3 A R1 R2 A(14) E7 E5 E8 E6 A`

**Porquê visitas e não ações soltas?** Uma visita é uma unidade com sentido: mover uma visita leva todos os itens dessa paragem juntos. Se mexêssemos em ações soltas, quase todos os vizinhos seriam absurdos. Por exemplo, entregar metade de uma encomenda num sítio e a outra metade noutro.

- `acoes_para_visitas()` converte as ações do Greedy em visitas.
- `visitas_para_acoes()` faz o inverso, para o verificador avaliar.
- O notebook confirma que converter para visitas e voltar dá exatamente as mesmas ações.

**O regresso final ao armazém fica sempre no fim** e não entra nos movimentos.

### 4.2 Vizinhos (`vizinhos()`, `aplicar()`)
| Movimento | Exemplo em `A B C D E` | Quantos vizinhos (n visitas) |
|---|---|---|
| `trocar(i, j)` | trocar(1, 3) → `A D C B E` | n(n−1)/2 |
| `mover(i, j)` | mover(1, 3) → `A C D B E` | ≈ n(n−2) |
| `inverter(i, j)` | inverter(1, 4) → `A E D C B` | (n−1)(n−2)/2 |
| `mover_bloco` (extra) | mover o bloco `B C` para o fim → `A D E B C` (também invertido: `A D E C B`) | mais vizinhos |

Os repetidos óbvios não são gerados. Mover para a posição seguinte é igual a trocar vizinhas, e inverter 2 visitas é igual a trocá-las.

### 4.3 Avaliação: o verificador como filtro (`avaliar()`)
Para cada vizinho, corre o `verificar_viabilidade` do `model.py`. Um vizinho só é **aceitável** se:
1. não tiver erros: janelas de recolha e entrega, capacidade, fluxo produtor → armazém → cliente e limite de 24 h no armazém;
2. a rota ficar **completa**: tudo o que é de hoje entregue, tudo o que foi recolhido descarregado e o veículo vazio no armazém.

**O custo é a distância em km** devolvida pelo verificador.

**Dado importante para a defesa:** só **0 a 3 % dos vizinhos são viáveis**. As regras são muito apertadas, por isso o filtro é essencial.

### 4.4 Hill-Climbing (`hill_climbing()`)
```
atual = rota do Greedy (tem de ser viável)
repetir:
    candidatos = vizinhos de atual que o verificador aprova e com menos km
    se não há candidatos: parar  → ótimo local
    atual = o melhor candidato (estratégia "melhor")
          ou o primeiro encontrado, numa ordem aleatória (estratégia "primeiro")
guardar o custo de cada iteração → curva custo × iteração
```

### 4.5 Dias encadeados (`PlanoLocal`)
Há um pormenor que é fácil esquecer: **o dia 30 influencia o dia 31.** Os itens recolhidos no dia 30 e entregues no dia 31 passam a noite no armazém, e o limite de 24 h conta a partir da hora a que chegaram.

Se o Hill-Climbing mudar a rota do dia 30, essas horas mudam e o dia 31 pode ficar inviável. Por isso:
- as rotas são otimizadas **por ordem cronológica** (primeiro todas as do dia 30, depois as do dia 31);
- ao otimizar o dia 30, um vizinho só é aceite se as rotas do dia 31 continuarem viáveis (`_dia_seguinte_ok()`);
- o dia 31 é otimizado com as horas de chegada reais do dia 30 já melhorado;
- no fim, `valido()` volta a verificar o plano inteiro.

### 4.6 Outras funções
- `perturbar()`: um passeio aleatório por vizinhos viáveis, que cria soluções iniciais piores e diferentes. Serve para testar o Hill-Climbing com várias sementes.
- `simulated_annealing()`: o extra. T₀ = 20 km, arrefecimento 0,995 e 3000 iterações por rota.
- `curva_total()`: junta as curvas das várias rotas na curva do custo total do plano.

---

## 5. Um exemplo passo a passo (tiny, veículo 1, dia 30)

1. **Rota do Greedy:** `R3 A R1 R2 A(14) E7 E5 E8 E6 A` → **278,73 km**
2. **Vizinhos gerados:** 128 (36 trocar, 64 mover, 28 inverter). **Só 2 são aprovados** pelo verificador.
   - Um exemplo rejeitado: `trocar(0, 1)` põe a ida ao armazém `A` antes da recolha `R3`. O veículo deixa de descarregar a meio da manhã, e as recolhas de `R3`, `R1` e `R2` ficam todas a bordo ao mesmo tempo. O verificador acusa excesso de capacidade (159 kg > 150 kg).
3. **Melhor vizinho:** `trocar(5, 6)`, que troca a ordem das entregas `E7` e `E5` → `R3 A R1 R2 A(14) E5 E7 E8 E6 A` → **273,07 km** (−5,66 km).
4. **Iteração seguinte:** nenhum vizinho melhora, por isso é um ótimo local, e neste caso coincide com o ótimo do A*.

---

## 6. Resultados (para apresentar)

### Tiny (ótimo do A* = 601,97 km)
- **A partir do Greedy:** 609,59 → **601,97 km** (ótimo), com 1 iteração em cada uma das 2 rotas, em cerca de 0,05 s.
- **10 soluções iniciais baralhadas** (623 km em média): o HC melhor, o HC primeiro e o SA chegam todos ao ótimo nas 10.

### Small (ótimo do A* = 879,45 km; 24 de 25 encomendas)
| Solução inicial | km inicial | HC (3 movimentos) | HC + mover bloco |
|---|---|---|---|
| Greedy H1 (pedido mais caro) | 880,53 | 880,53 (já é ótimo local) | **879,45** |
| Greedy H2 (MST) | 940,42 | 880,53 (−59,89) | **879,45** |
| Greedy "mais distante" | 913,58 | **879,45** | **879,45** |

**10 soluções baralhadas** (935 km em média):

| Método | Vezes no ótimo | Chamadas ao verificador (média) |
|---|---|---|
| HC melhor | 1/10 | 1688 |
| HC primeiro | 1/10 | 1181 |
| SA (extra) | 1/10 | 12004 |
| **HC melhor + mover bloco** | **10/10** | 5641 |

### Movimentos usados nas melhorias
trocar 47,5 % · mover 48,5 % · inverter 4 %

---

## 7. Como explicar cada gráfico

1. **"Hill-Climbing a partir do Greedy" (tiny e small):** cada ponto é uma iteração. A curva desce sempre ou fica igual, porque o Hill-Climbing nunca aceita pioras. A linha tracejada é o ótimo do A*. No small, a curva azul (Greedy H1) é um só ponto: já era um ótimo local.
2. **"Solução inicial baralhada" (HC melhor contra HC primeiro):** o "melhor" desce em degraus maiores e chega lá em menos iterações. O "primeiro" dá mais passos, mas mais pequenos e mais baratos.
3. **"Simulated Annealing por rota":** a linha laranja (custo atual) às vezes sobe acima da azul (o melhor até agora). São as pioras aceites quando a temperatura está alta. Depois estabiliza.
4. **"Com e sem mover bloco":** as duas curvas coincidem até ao penúltimo passo. A seguir, só a versão com mover bloco consegue o último passo até ao ótimo.

---

## 8. Perguntas prováveis na defesa (e respostas)

**P: Porque é que o Hill-Climbing não garante o ótimo?**
R: Porque para no primeiro ótimo local. Só olha para os vizinhos e nunca aceita pioras. No small isso viu-se: ficou a 1,08 km do ótimo.

**P: Porque é que ficou preso a 1,08 km?**
R: A rota ótima tem as mesmas visitas, mas duas entregas (`E10` e `E9`) mais cedo, logo a seguir a `R4`. Para lá chegar, era preciso mudar as duas ao mesmo tempo. Cada mudança isolada ou viola as janelas ou piora os km, por isso o Hill-Climbing não a aceita.

**P: Como resolveste isso?**
R: Com um 4.º movimento, *mover bloco* (or-opt), que move 2 ou 3 visitas seguidas de uma vez, na mesma ordem ou invertidas. Com ele, chega ao ótimo em 10 de 10 tentativas. Em troca, faz cerca de 3 vezes mais avaliações.

**P: Como garantes que as rotas são válidas?**
R: Cada vizinho passa pelo `verificar_viabilidade` do `model.py`, que verifica janelas, capacidade, fluxo e as 24 h, e tem de ficar completo. No fim, o plano inteiro é verificado outra vez, com os dois dias encadeados.

**P: Qual é a diferença entre "melhor vizinho" e "primeira melhoria"?**
R: O "melhor" avalia todos os vizinhos e escolhe o melhor: menos iterações, mas mais caras. O "primeiro" aceita o primeiro que melhora: mais iterações, mas faz 25–30 % menos avaliações. Neste problema chegaram aos mesmos resultados finais.

**P: Porque é que o Simulated Annealing não fez melhor?**
R: Porque quase todos os vizinhos são inviáveis (menos de 3 % são aprovados). O SA só pode aceitar pioras entre vizinhos viáveis, por isso tem pouca margem para escapar. Com mais afinação (temperatura, arrefecimento) talvez ajudasse. Neste caso, uma vizinhança maior (mover bloco) foi mais eficaz.

**P: O que é a "função de custo"?**
R: São os km totais da rota, calculados pelo verificador com a matriz de distâncias original.

**P: Porque é que o dia 30 não pode ser otimizado sozinho?**
R: Por causa do limite de 24 h no armazém. Mudar a rota do dia 30 muda a hora de chegada dos itens que ficam lá a noite, e isso pode tornar o carregamento do dia 31 inviável. Por isso só aceito mudanças que mantêm o dia 31 viável.

**P: Porque é que o inverter quase nunca é usado?**
R: Porque inverter um troço inteiro muda a ordem de várias visitas ao mesmo tempo, e com janelas temporais apertadas isso quase sempre torna a rota inviável.

**P: Qual é a complexidade de uma iteração?**
R: Com n visitas, há cerca de n²/2 trocas + n² movimentos + n²/2 inversões, ou seja, O(n²) vizinhos. Cada um é avaliado pelo verificador em O(tamanho da rota). No small, n anda pelas 10 a 17 visitas, por isso cada execução leva menos de 0,5 s.

**P: O que melhorarias?**
R: Quatro coisas:
1. Movimentos que mudam o agrupamento (partir ou juntar visitas) e que passam encomendas de um veículo para o outro.
2. Otimizar os dois dias em conjunto.
3. Afinar o Simulated Annealing.
4. Reinícios aleatórios.

---

## 9. Para o André (integração)

```python
import sys; sys.path.insert(0, "pesquisa_local")
from local import PlanoLocal, MOVIMENTOS, MOVIMENTOS_COM_BLOCO, curva_total

# entradas = uma por (veículo, dia), vindas do Greedy:
# dict(vehicle_id=..., dia=date, hora_partida=datetime, recolher=set(itens),
#      entregar=set(itens), acoes=[("pickup", i), ("warehouse", A), ("load", i), ("delivery", i), ...])
plano = PlanoLocal.de_acoes(problem, entradas)
custo_inicial = plano.custo_total()
res = plano.otimizar("hc", estrategia="melhor")          # ou movimentos=MOVIMENTOS_COM_BLOCO
curva = curva_total(res, custo_inicial)                  # custo total por iteração, para o gráfico
print(res["custo_total_km"], res["valido"])
```

---

## 10. Glossário rápido
- **Vizinho:** solução obtida com um movimento.
- **Viável:** aprovado pelo verificador.
- **Ótimo local:** sem vizinhos melhores.
- **Ótimo global:** a melhor solução possível (aqui, a do A*).
- **Steepest ascent:** escolher o melhor vizinho.
- **First improvement:** aceitar o primeiro vizinho que melhora.
- **2-opt:** inverter um troço da rota.
- **Or-opt:** mover um bloco de visitas seguidas.
- **Simulated Annealing:** aceita pioras com probabilidade que diminui com a "temperatura".
- **Semente:** número que fixa a aleatoriedade, para os resultados serem reprodutíveis.
