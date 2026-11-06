# Pesquisa e otimização da frota — IA26_P01_G02

## 1. Objetivo

Este módulo procura rotas eficientes para **os dois veículos**, distribuindo encomendas completas entre eles e minimizando a distância total percorrida. A solução respeita o fluxo produtor → armazém → local de entrega, as janelas temporais, a capacidade dos veículos e o tempo máximo de permanência dos produtos no armazém.

Cada veículo pode fazer **várias viagens ao armazém**. A capacidade limita a carga transportada em cada viagem, não o peso total de todas as encomendas atribuídas ao veículo.

## 2. Organização do código

- **`model.py`** — carrega os CSV, representa pedidos, veículos e estados, verifica a viabilidade de cada rota e valida a atribuição e a cobertura conjunta dos dois veículos.
- **`pesquisa.py`** — implementa os sucessores, UCS, Greedy, A*, as heurísticas H1/H2, a pesquisa individual por veículo e a otimização conjunta da frota.

## 3. Como funciona o modelo

O estado de pesquisa guarda a posição atual do veículo, a hora, a carga e a fase em que se encontra cada item.

O fluxo logístico é:

1. **Recolha (`pickup`)** — recolher produtos nos produtores, quando estão disponíveis.
2. **Descarregar (`warehouse`)** — regressar ao armazém e descarregar os produtos recolhidos.
3. **Carregar (`load`)** — carregar encomendas completas que estejam no armazém e respeitem a capacidade e o limite de permanência.
4. **Entrega (`delivery`)** — entregar cada encomenda no respetivo destino.
5. **Regresso ao armazém** — terminar a rota no armazém, sem carga ou itens por entregar.

Os itens de uma mesma encomenda são atribuídos ao mesmo veículo e tratados em conjunto. A pesquisa pode fazer várias viagens, pelo que a soma do peso das encomendas atribuídas pode ser superior à capacidade do veículo.

## 4. Algoritmos e heurísticas

Todos os algoritmos minimizam a distância percorrida em quilómetros:

| Algoritmo | Critério de escolha | Garantia |
|---|---|---|
| **UCS** | Menor custo acumulado `g(n)`. | Encontra a rota de menor distância se a pesquisa terminar sem limites. |
| **Greedy Best-First** | Menor estimativa `h(n)`. | Procura rapidamente, mas não garante a rota mais curta. |
| **A\*** | Menor `f(n) = g(n) + h(n)`. | Pode encontrar a rota ótima quando a heurística é admissível e a pesquisa termina. |

As heurísticas usadas pelo Greedy e pelo A* são:

- **H1 — Pedido mais caro (`h1_pedido_mais_caro`):** calcula o custo mínimo obrigatório que falta para cada item pendente e usa o maior desses custos.
- **H2 — Árvore Geradora Mínima (`h2_mst`):** calcula uma estimativa para ligar as paragens ainda necessárias, usando uma MST construída com Prim.

A duração, os tempos de serviço, as janelas e a permanência no armazém são usados para verificar a viabilidade. O objetivo de otimização é a distância, não o tempo total.

## 5. Otimização conjunta dos dois veículos

A função `otimizar_frota(...)` faz o seguinte:

1. Agrupa os itens por encomenda.
2. Gera distribuições em que cada encomenda completa fica atribuída a um único veículo.
3. Calcula uma rota para cada veículo usando UCS, Greedy ou A*.
4. Verifica se os dois veículos, em conjunto, entregam todos os itens exatamente uma vez.
5. Soma as distâncias das duas rotas e guarda a distribuição com menor distância total.

A função `comparar_algoritmos_frota(...)` repete este processo para os cinco cenários: UCS, Greedy H1, Greedy H2, A* H1 e A* H2. Cada método pode encontrar uma distribuição diferente.

### Limites da otimização

A distribuição de encomendas pode ter muitas combinações. Com 25 encomendas que possam ser atribuídas a qualquer veículo, existem até `2^25 - 2` distribuições em que ambos os veículos recebem pelo menos uma encomenda. Por isso:

- `max_particoes=None` explora todas as distribuições viáveis;
- um valor como `max_particoes=128` limita a análise às primeiras 128 distribuições geradas;
- `max_nos_expandidos_por_veiculo` limita a pesquisa da rota de cada veículo.

Quando um limite é atingido, o resultado é a **melhor solução encontrada entre as distribuições avaliadas**, não uma prova de ótimo global. A função só assinala `otimo_global_comprovado=True` quando todas as distribuições foram avaliadas, as pesquisas terminaram sem limites internos e foi usado UCS.

O planeamento recebe um único instante de partida e pode incluir itens com janelas em vários dias. As próprias janelas temporais e a regra das 24 horas são verificadas. Não existe, neste modelo, uma restrição adicional de horário de turno ou pausa diária dos motoristas.

## 6. Executar

Instala a dependência:

```bash
pip install pandas
```

Coloca os 12 CSV na pasta do conjunto de dados, por exemplo `docs/data_tiny/`, e executa o código a partir da pasta onde estão `model.py` e `pesquisa.py`.

### Otimização exaustiva do conjunto tiny

```python
from datetime import datetime
from model import Problem
from pesquisa import otimizar_frota, tabela_resultado_frota

problem = Problem("docs/data_tiny")
itens = set(problem.pedidos)  # todos os itens / todas as encomendas
hora_partida = min(req.availability_start for req in problem.pedidos.values())

resultado = otimizar_frota(
    problem,
    itens_objetivo=itens,
    hora_partida=hora_partida,
    algoritmo="ucs",
    max_particoes=None,  # testar todas as distribuições
    max_nos_expandidos_por_veiculo=None,  # não interromper a pesquisa de rotas
)

print(resultado["nota"])
print("Distância total:", resultado["melhor_solucao"]["distancia_total_km"], "km")
print(tabela_resultado_frota(resultado).to_string(index=False))
```

Esta configuração é indicada para o conjunto **tiny**, caso o número de distribuições e o esforço de pesquisa sejam comportáveis. O UCS é usado para permitir a prova de ótimo global quando a enumeração e todas as pesquisas terminam.

### Comparação dos cinco métodos

```python
from pesquisa import comparar_algoritmos_frota

tabela, detalhes = comparar_algoritmos_frota(
    problem,
    itens_objetivo=itens,
    hora_partida=hora_partida,
    max_particoes=128,
    max_nos_expandidos_por_veiculo=100_000,
)

print(tabela.to_string(index=False))
```

Para o conjunto **small**, que tem 25 encomendas e abrange dois dias, recomenda-se começar com um limite de partições e de nós. Aumenta os limites gradualmente, conforme o tempo e a memória disponíveis. Usar `max_particoes=None` nesse conjunto pode implicar dezenas de milhões de distribuições.

### Pesquisa individual e comparação por veículo

As funções `ucs`, `greedy_search`, `a_star_search` e `comparar_algoritmos` continuam disponíveis para estudar uma rota individual, por exemplo para produzir uma solução inicial Greedy que será depois melhorada pelo Hill-Climbing.

## 7. Interpretar os resultados

- **Distância total (km):** soma da distância dos dois veículos; é o principal critério de otimização.
- **Nós expandidos/gerados:** esforço de pesquisa.
- **Tempo (s):** tempo de execução.
- **Partições avaliadas:** número de distribuições de encomendas efetivamente testadas.
- **Partições viáveis:** distribuições para as quais foram encontradas duas rotas completas e válidas.
- **Ótimo global comprovado:** só é verdadeiro quando a enumeração é completa e as pesquisas UCS terminam sem limites.

Uma execução interrompida por limite não prova que não existe uma solução. Da mesma forma, a melhor solução encontrada numa enumeração parcial não deve ser apresentada como ótimo global.

## 8. Limitações e pressupostos

- A otimização conjunta trabalha com exatamente dois veículos.
- Cada encomenda completa é atribuída a um único veículo. Se existirem itens dessa encomenda já armazenados, a encomenda fica fixada ao veículo correspondente.
- A pesquisa da rota é executada separadamente para cada veículo; a otimização conjunta compara depois a soma das distâncias. Não modela conflitos de utilização simultânea do armazém nem horários de turno que não estejam definidos nas regras fornecidas.
- A geração de combinações e a enumeração de distribuições crescem rapidamente com o número de encomendas.
- Os testes realizados durante o desenvolvimento usam instâncias sintéticas. Antes de apresentar resultados finais, é necessário executar os módulos com os CSV oficiais `tiny` e `small`.
