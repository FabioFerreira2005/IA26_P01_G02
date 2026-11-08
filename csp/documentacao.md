# Documentação — CSP de atribuição de encomendas

## 1. Objetivo e lugar no projeto

O módulo `csp.py` formula a atribuição de encomendas a veículos como um
problema de satisfação de restrições (CSP). A CSP recebe uma instância `Problem`
carregada por `model.py`, agrupa os itens por encomenda e procura atribuir cada
encomenda completa a um veículo elegível.

No fluxo de integração previsto, a atribuição da CSP pode servir de ponto de
partida para a pesquisa de rotas. A CSP não constrói a rota conjunta nem prova
que todas as encomendas atribuídas ao mesmo veículo podem ser executadas na
mesma sequência. A rota produzida pela pesquisa continua a ter de passar pelo
verificador de `model.py`.

## 2. Formulação do CSP

### 2.1 Variáveis

Há uma variável por `order_id`. O domínio desta variável é o conjunto de IDs dos
veículos que podem receber a encomenda.

Os itens da mesma encomenda não são variáveis separadas. Assim, a encomenda
permanece inteira e não pode ser dividida por veículos diferentes. O construtor
`FleetCSP` valida que, se forem fornecidos `item_ids`, todos os itens de cada
encomenda incluída estão presentes.

### 2.2 Domínios

Para cada encomenda e veículo, o construtor verifica:

1. **Capacidade por encomenda:** o peso da encomenda tem de caber numa viagem do
   veículo. Esta verificação é aplicada nos dois modos de capacidade.
2. **Compatibilidade:** se os pedidos tiverem o atributo
   `requires_refrigeration=True`, o veículo tem de ser refrigerado.
3. **Janelas temporais individuais:** tem de existir uma sequência de recolhas
   nos produtores, passagem pelo armazém e entrega que respeite as janelas da
   encomenda quando esta é planeada sozinha.

O dataset atual não contém um requisito de refrigeração por produto. Por isso,
esta versão não infere compatibilidade pela categoria do produto. Atualmente,
essa regra não remove veículos dos domínios.

### 2.3 Janelas temporais

A função `_temporalmente_viavel_isolada` agrupa os itens da encomenda por local
de recolha e procura uma ordem viável para visitar esses locais. Usa programação
dinâmica sobre subconjuntos: para cada conjunto de produtores visitados e cada
último produtor, guarda a hora mais cedo em que o serviço pode terminar.

Em cada produtor:

- a chegada é calculada com `problem.tempo_entre`;
- o início do serviço é o máximo entre a chegada e as disponibilidades dos
  itens desse produtor;
- o início tem de estar dentro das janelas de todos esses itens;
- o serviço ocupa `problem.tempo_servico_min`.

Depois das recolhas, a verificação considera o regresso ao armazém, o tempo de
descarga, o tempo de carregamento e a deslocação ao destino. O início do
serviço de entrega tem de respeitar todas as janelas de entrega dos itens da
encomenda.

Por omissão, o planeamento começa à meia-noite da data `start_date` definida
nas regras. Se essa regra não existir, usa a primeira disponibilidade dos
itens selecionados. Também é possível passar `planning_start` explicitamente.

**Limite:** esta verificação é feita para uma encomenda de cada vez. Não
considera o tempo que o veículo gastaria a cumprir outras encomendas antes ou
depois dela, nem conflitos temporais entre encomendas atribuídas ao mesmo
veículo. Consequentemente, um domínio individualmente viável não garante uma
rota de frota viável.

### 2.4 Capacidade: dois âmbitos

Os métodos aceitam `capacity_mode`:

| Modo | Restrição de capacidade | Uso indicado |
|---|---|---|
| `single_load` | A soma dos pesos atribuídos a cada veículo não pode exceder a capacidade. | Experiência CSP simples em que cada veículo recebe uma única carga. |
| `multi_trip` | Cada encomenda tem de caber numa viagem; o total atribuído pode exceder a capacidade do veículo. | Integração com o modelo atual, que permite regressar ao armazém entre viagens. |

Os métodos usam `single_load` por omissão. Para representar a semântica de
várias viagens do modelo de rotas, passe `capacity_mode="multi_trip"` de forma
explícita. No dataset `small`, o peso total é 580 kg e a capacidade agregada
dos dois veículos é 350 kg; por isso, `single_load` não pode atribuir todas as
encomendas. Em `multi_trip`, a capacidade é verificada por encomenda e o
planeador de rotas decide como transportar as encomendas em várias viagens.

## 3. Restrição suave: equilíbrio de carga

O balanceamento é uma preferência, não uma restrição rígida. Para cada veículo,
calcula-se a utilização normalizada:

```text
utilização = peso atribuído / capacidade do veículo
```

O `balance_score` é a diferença entre a maior e a menor utilização. Um valor
menor indica uma distribuição mais equilibrada.

No backtracking próprio, os veículos são ordenados pelo score que resultaria de
cada escolha. A pesquisa tenta primeiro a escolha mais equilibrada, mas mantém
as restantes alternativas se essa escolha não permitir completar a atribuição.
O backtracking devolve a primeira solução encontrada; não garante que seja a
atribuição globalmente mais equilibrada.

Com `python-constraint`, as soluções são enumeradas até ao limite
`max_solutions` e é escolhida a de menor `balance_score` entre as enumeradas.
Se o limite for atingido, `optimal_balance_proven` fica falso, pois pode haver
uma solução ainda mais equilibrada fora do conjunto examinado.

## 4. Métodos de resolução

### 4.1 `python-constraint`

`solve_python_constraint(...)` cria uma variável por encomenda, aplica os
domínios elegíveis e, no modo `single_load`, aplica a restrição global de
capacidade por veículo. Depois percorre as soluções e guarda a mais equilibrada
entre as consideradas.

Parâmetros principais:

- `capacity_mode`: `single_load` ou `multi_trip`;
- `max_solutions`: máximo de atribuições a examinar; por omissão, 10 000. Use
  `None` para enumerar todas as soluções.

O campo `optimal_balance_proven` indica se a enumeração terminou antes de
atingir o limite e se foi possível comprovar o melhor equilíbrio entre todas
as soluções viáveis.

### 4.2 Backtracking próprio

`solve_backtracking(...)` percorre atribuições recursivamente. Em
`single_load`, atualiza a carga dos veículos e descarta escolhas que ultrapassem
a capacidade. Também verifica se o peso restante ainda cabe na capacidade
residual agregada.

O argumento `use_mrv` escolhe a ordem das variáveis:

- `False`: escolhe sempre a encomenda de menor `order_id` ainda não atribuída;
- `True`: aplica **MRV (Minimum Remaining Values)**, escolhendo a encomenda
  com menos veículos ainda possíveis naquele estado. Em caso de empate,
  prioriza encomendas mais pesadas, prazos mais próximos e, por fim, o ID.

Em ambos os casos, a ordem dos valores do domínio usa o balanceamento suave.
O resultado inclui:

- `nodes`: estados de recursão visitados;
- `backtracks`: ramos abandonados por não conduzirem a uma atribuição completa;
- `loads_kg` e `balance_score`: resumo da solução encontrada.

### 4.3 Comparar os dois backtrackings

`compare_backtracking(csp, capacity_mode=...)` executa o backtracking estático
e o backtracking com MRV e devolve os dois `CSPResult`.

O número de backtracks depende da instância, da ordem das variáveis e da
heurística de valores. Nos datasets atuais, todos os domínios contêm os dois
veículos e a heurística encontra uma solução logo no primeiro ramo; ambos os
métodos reportam zero backtracks. Isto cumpre a contagem, mas não demonstra uma
redução de esforço por MRV. Para analisar a diferença, é útil incluir uma
instância de demonstração com domínios de tamanhos diferentes ou uma capacidade
mais restritiva.

## 5. API e exemplos

### 5.1 Criar a CSP

```python
from model import Problem
from csp.csp import FleetCSP

problem = Problem("docs/data_tiny")
csp = FleetCSP(problem)

print(csp.domains)
```

É possível limitar o conjunto de itens e veículos. Os itens selecionados têm
de incluir todas as linhas das encomendas correspondentes:

```python
csp = FleetCSP(
    problem,
    item_ids=set(problem.pedidos),
    vehicle_ids=(1, 2),
)
```

### 5.2 Resolver com `python-constraint`

```python
resultado = csp.solve_python_constraint(
    capacity_mode="single_load",
    max_solutions=5_000,
)

print(resultado.feasible)
print(resultado.assignment)  # order_id -> vehicle_id
print(resultado.loads_kg)
print(resultado.balance_score)
print(resultado.optimal_balance_proven)
```

### 5.3 Resolver e comparar backtracking

```python
from csp.csp import compare_backtracking

comparacao = compare_backtracking(csp, capacity_mode="single_load")
for resultado in comparacao:
    print(resultado.method, resultado.nodes, resultado.backtracks)
```

Para o modelo com várias viagens:

```python
resultado = csp.solve_backtracking(
    use_mrv=True,
    capacity_mode="multi_trip",
)
```

### 5.4 Interpretar `assignment`

O dicionário `assignment` tem a forma:

```python
{order_id: vehicle_id}
```

Para entregar os itens por veículo a uma fase seguinte:

```python
itens_por_veiculo = {vehicle_id: set() for vehicle_id in csp.vehicle_ids}
for order_id, vehicle_id in resultado.assignment.items():
    itens = next(task.item_ids for task in csp.tasks if task.order_id == order_id)
    itens_por_veiculo[vehicle_id].update(itens)
```

Esta atribuição pode então alimentar a pesquisa de rotas. O sucesso da CSP não
deve ser interpretado como prova de que as rotas resultantes são viáveis.

## 6. Resultados de referência

Na execução de referência com as dependências do projeto:

- **Tiny:** 12 encomendas, todas com domínio `{1, 2}`. O `python-constraint`
  enumerou 2 257 atribuições viáveis em `single_load` e encontrou cargas de
  115,7 kg e 154,3 kg. A enumeração terminou, logo `optimal_balance_proven`
  ficou verdadeiro para o score de equilíbrio.
- **Backtracking em tiny:** sem MRV e com MRV encontraram atribuições com 13
  estados visitados e zero backtracks. A solução com MRV teve score de
  equilíbrio inferior nesta execução.
- **Small:** 25 encomendas, todas com domínio `{1, 2}`. Em `multi_trip`, o
  backtracking encontrou uma atribuição com cargas de 260,5 kg e 319,5 kg.

Estes são resultados de atribuição, não resultados de rota. Antes da entrega
final, a integração deve verificar a rota de cada veículo e registar se a CSP
precisou de produzir outra atribuição após uma falha do planeador.

## 7. Notebook

O notebook [`01_csp.ipynb`](01_csp.ipynb) apresenta:

1. a definição de variáveis e domínios;
2. as restrições duras e a heurística suave;
3. uma execução com `python-constraint`;
4. um exemplo de atribuição em `multi_trip`;
5. a comparação de backtracking estático e MRV;
6. perguntas para orientar a análise dos resultados.

Na raiz do repositório, executar:

```bash
pip install -r requirements.txt
jupyter notebook csp/01_csp.ipynb
```

## 8. Limitações e próximos passos de integração

1. **Compatibilidade:** decidir com o grupo quais os atributos reais que
   restringem um veículo. O dataset atual não liga produtos à refrigeração.
2. **Janelas entre encomendas:** acrescentar restrições que detetem
   incompatibilidades temporais entre tarefas no mesmo veículo, ou usar a CSP
   num ciclo: atribuir, planear, verificar e voltar a procurar se a rota falhar.
3. **Capacidade:** manter explícito qual o modo usado. Para integrar com o
   modelo que permite várias viagens, usar `multi_trip` ou modelar as viagens
   como variáveis/tarefas.
4. **MRV:** acrescentar um exemplo com domínios assimétricos e restrições que
   provoquem backtracking, para que a comparação de contagens seja informativa.
5. **Resultados finais:** não apresentar uma atribuição como solução completa
   sem a validação das rotas e das janelas pelo verificador do modelo.
