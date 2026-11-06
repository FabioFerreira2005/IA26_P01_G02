# IA26_P01_G02 — Estado atual do projeto e model.py

## 1. Objetivo do projeto

O objetivo deste projeto é desenvolver um agente inteligente capaz de encontrar rotas eficientes para a distribuição de produtos locais, ligando produtores, um centro de recolha (armazém) e clientes.

O agente tem de determinar quais os produtos a recolher, que veículos utilizar e em que ordem visitar os diferentes locais, procurando minimizar a distância percorrida e respeitando as restrições do problema.

As principais restrições são:

- **Fluxo obrigatório:** todos os produtos têm de seguir o percurso produtor → armazém → local de entrega.
- **Janelas temporais:** cada produto tem uma janela de disponibilidade para recolha e uma janela para entrega.
- **Capacidade:** cada veículo tem um limite máximo de carga em kg.
- **Tempos de serviço:** 10 minutos por visita a uma paragem de recolha ou entrega e 15 minutos para descarregar ou carregar no armazém.
- **Permanência no armazém:** cada produto não pode permanecer no armazém mais de 24 horas, contadas desde a chegada até ao início do carregamento.

## 2. Trabalho já realizado

### 2.1. EDA — Análise Exploratória dos Dados

Foi desenvolvido o notebook `01_eda_small.ipynb`, onde analisámos os 12 ficheiros CSV do conjunto de dados *small*.

A análise incluiu:

- Carregamento e exploração das tabelas.
- Verificação da integridade dos dados e das relações entre identificadores.
- Análise dos produtores, produtos, clientes, veículos e locais de entrega.
- Análise dos pesos dos produtos e das capacidades dos veículos.
- Estudo das janelas temporais de recolha e entrega.
- Análise da matriz de distâncias e tempos de viagem.
- Cálculo das folgas temporais e das permanências dos produtos no armazém.
- Comparação entre os conjuntos *tiny* e *small*.

Algumas conclusões importantes:

- O conjunto *small* contém 14 paragens, 25 encomendas e 80 itens.
- Existem 2 veículos, com capacidades de 250 kg e 300 kg.
- O peso total dos produtos é de 580 kg.
- As recolhas e entregas têm de ser distribuídas por vários percursos, respeitando as capacidades e as janelas temporais.
- A permanência máxima de 24 horas no armazém é uma restrição importante.

A EDA permite-nos perceber melhor o problema antes de implementar os algoritmos de pesquisa.

### 2.2. Modelação — model.py

Depois da análise dos dados, começámos a transformar a informação dos CSV numa estrutura que possa ser utilizada pelos algoritmos.

O ficheiro `model.py` é a base da futura implementação do Greedy, UCS e A*.

A sua função não é encontrar diretamente a melhor rota. É disponibilizar os dados, representar os pedidos e veículos, calcular custos e verificar se as rotas respeitam as regras.

## 3. Como funciona o model.py

O ficheiro está organizado em quatro componentes principais.

### 3.1. Carregamento e preparação dos dados

Começamos por ter três funções:

- `carregar_dados(pasta)` — lê os 12 ficheiros CSV e converte as colunas temporais para o formato datetime.
- `paragem_armazem(dados)` — identifica a localização do centro de recolha.
- `construir_pedidos(dados)` — junta a informação dos itens, produtos, encomendas e localizações numa tabela consolidada.

A ideia é evitar que os algoritmos tenham de andar constantemente a consultar e cruzar diferentes ficheiros CSV.

Depois desta preparação, temos toda a informação necessária para criar os objetos do modelo.

### 3.2. Classes Request e Vehicle

Estas duas classes representam os elementos principais do problema.

**Request**

Representa um item de encomenda, guardando:

- Identificador do item e da encomenda.
- Nome do produto.
- Peso em kg.
- Localização do produtor.
- Localização de entrega.
- Janela de disponibilidade.
- Janela de entrega.

**Vehicle**

Representa um veículo, guardando:

- Identificador e matrícula.
- Capacidade máxima em kg.
- Informação sobre refrigeração.
- Velocidade média.
- Localização do armazém onde está sediado.

Utilizamos `@dataclass(frozen=True)` porque estes dados são essencialmente fixos durante a execução dos algoritmos.

### 3.3. Classe Problem

Esta é a classe central da modelação.

Recebe o caminho da pasta dos dados e constrói as estruturas que serão utilizadas pelos algoritmos.

Entre outras informações, guarda:

- `problem.armazem` — localização do armazém.
- `problem.paragens` — informação das diferentes paragens.
- `problem.regras` — regras operacionais do dataset.
- `problem.veiculos` — dicionário de veículos.
- `problem.pedidos` — dicionário de pedidos.
- `problem.distancia` — distâncias entre pares de localizações.
- `problem.tempo` — tempos de viagem entre pares de localizações.

Também disponibiliza três funções importantes:

**`distancia_entre(origem, destino)`**

-> Devolve a distância em km entre duas paragens.

**`tempo_entre(origem, destino)`**

-> Devolve o tempo de viagem em minutos entre duas paragens.

**`custo_rota(paragens_rota)`**

-> Calcula a distância total e o tempo total de condução de uma sequência de paragens.

Por exemplo, para uma rota:

`[7, 3, 6, 7]`

A função soma as distâncias e tempos entre 7 → 3, 3 → 6 e 6 → 7.

O custo utilizado futuramente pelo A* será a distância acumulada em quilómetros.

### 3.4. Verificação da viabilidade — verificar_viabilidade()

Esta função simula uma rota e verifica se respeita as restrições do problema.

As ações disponíveis são:

| Ação | Significado |
|---|---|
| `("pickup", item_id)` | Recolher um produto no produtor |
| `("warehouse", armazem_id)` | Regressar ao armazém e descarregar os produtos recolhidos |
| `("load", item_id)` | Carregar um produto que já está no armazém |
| `("delivery", item_id)` | Entregar o produto ao cliente |

A função recebe o veículo, a sequência de ações e a hora de partida. Também permite indicar produtos que já se encontram no armazém, por exemplo, produtos recolhidos no dia anterior.

Durante a simulação, atualiza:

- Localização atual do veículo.
- Relógio e duração da viagem.
- Distância percorrida.
- Peso transportado.
- Produtos recolhidos.
- Produtos armazenados.
- Produtos carregados para entrega.
- Produtos entregues.

Também verifica as janelas temporais, a capacidade do veículo, a passagem obrigatória pelo armazém e a permanência máxima de 24 horas.

No fim do teste, a função devolve um dicionário com a viabilidade, os erros encontrados, a distância, a duração, a hora de fim e os produtos entregues.

## 4. Classe State — preparação para os algoritmos

A classe `State` representa uma situação específica durante a construção de uma rota.

É especialmente importante para os algoritmos de pesquisa, porque cada estado representa aquilo que o veículo já fez e aquilo que ainda falta fazer.

Contém:

| Atributo | Significado |
|---|---|
| `paragem_atual` | Localização atual do veículo |
| `tempo_atual` | Hora atual da simulação |
| `carga_atual_kg` | Peso atualmente transportado |
| `recolhidos_a_bordo` | Produtos recolhidos ainda não descarregados |
| `no_armazem` | Produtos que se encontram no armazém |
| `para_entrega_a_bordo` | Produtos carregados para entrega |
| `entregues` | Produtos já entregues |
| `distancia_acumulada_km` | Distância já percorrida |
| `historico_paragens` | Histórico das localizações visitadas |
| `chegadas_armazem` | Hora de chegada de cada produto ao armazém |

O último atributo foi acrescentado para resolver uma questão importante: dois produtos podem estar no armazém, mas ter chegado em momentos diferentes.

Ao guardar a hora de chegada de cada um, conseguimos verificar individualmente se algum ultrapassa as 24 horas de permanência.

A classe também possui o método `paragens_pendentes()`, que identifica as localizações que ainda falta visitar para concluir os produtos pretendidos.

O `State` é imutável (`frozen=True`), para evitar que a criação de um novo estado altere acidentalmente o estado anterior.

**Atenção:** quando implementarmos os sucessores dos algoritmos, teremos de atualizar corretamente todos estes atributos, especialmente `chegadas_armazem`.

## 5. Heurística h_mais_distante()

Aqui vou explicar a heurística proposta por mim (Fábio): `h_mais_distante()`.

O veículo tem várias paragens pendentes. No mínimo, terá de visitar cada uma delas e, no final, regressar ao armazém.

Em vez de tentar calcular toda a rota, a heurística procura a paragem pendente que representa o maior limite inferior de distância.

A fórmula utilizada é:

**h(n) = max [d(n,p) + d(p,A)]**

Onde:

- `n` representa a posição atual do veículo.
- `p` representa uma paragem pendente.
- `A` representa o armazém.
- `d(x,y)` representa a distância mínima entre duas localizações.

### Exemplo simples

Imaginemos que:

- O veículo está no armazém.
- Ainda tem de visitar o produtor A.
- Ainda tem de visitar o local de entrega B.
- No final tem de regressar ao armazém.

Suponhamos as seguintes distâncias mínimas:

| Percurso | Distância |
|---|---:|
| Armazém → Produtor A | 10 km |
| Produtor A → Armazém | 10 km |
| Armazém → Entrega B | 15 km |
| Entrega B → Armazém | 15 km |

A heurística calcula:

- Para o produtor A: 10 + 10 = 20 km.
- Para a entrega B: 15 + 15 = 30 km.

Escolhe o maior valor:

**h(n) = 30 km**

Isto não significa que a rota inteira custe 30 km. Significa que, mesmo no melhor cenário, o veículo terá de percorrer pelo menos essa distância para visitar uma das paragens pendentes e regressar ao armazém.

Por isso, esta estimativa funciona como um limite inferior do custo que ainda falta percorrer.

### Porque utilizamos Floyd-Warshall?

Na EDA identificámos pequenas violações da desigualdade triangular na matriz original, devido a arredondamentos.

Para evitar que essas diferenças provoquem uma sobrestimação da distância na heurística, foi criada uma matriz auxiliar `distancia_minima`, calculada com Floyd-Warshall.

Esta matriz guarda as menores distâncias entre todas as paragens.

É importante perceber que **não substitui a matriz original utilizada para calcular os custos reais das rotas**. Serve apenas para obter distâncias mínimas para a heurística.

A heurística assume que uma rota completa termina no armazém.

No A*, será utilizada juntamente com o custo já percorrido:

**f(n) = g(n) + h(n)**

- `g(n)` — distância que o veículo já percorreu.
- `h(n)` — estimativa da distância mínima que ainda falta percorrer.
- `f(n)` — custo estimado total da solução através daquele estado.

Esta heurística está preparada como limite inferior de distância. A sua utilização no algoritmo deve manter a condição de regresso ao armazém e a representação correta dos estados.

## 6. Testes manuais

Já existem três testes iniciais para validar o comportamento do modelo:

1. **Rota viável:** recolher dois produtos, regressar ao armazém, carregar os produtos, entregar e regressar ao armazém.
2. **Rota inviável:** tentar entregar diretamente do produtor ao cliente, sem passar pelo armazém.
3. **Rota inviável:** iniciar a viagem demasiado tarde e violar as janelas temporais.

Estes testes permitem verificar se as principais regras estão a ser respeitadas.

Antes de avançar, devemos complementar os testes com casos de excesso de capacidade, permanência superior a 24 horas, recolhas na mesma localização e rotas incompletas.

## 7. O que falta desenvolver

A modelação constitui a base para a fase seguinte, mas ainda não temos os algoritmos de pesquisa implementados.

Os próximos passos são:

### 7.1. Pesquisa informada

Implementar:

- Estado inicial de cada veículo.
- Geração de estados sucessores e ações possíveis.
- Verificação das restrições durante a expansão.
- Teste de objetivo.
- Greedy Best-First Search.
- Pesquisa de Custo Uniforme (UCS).
- A*.
- Segunda heurística. (?)
- Contagem de nós expandidos.
- Comparação dos resultados e das rotas encontradas.

O objetivo é encontrar rotas para os dois veículos do conjunto *tiny*, conforme o enunciado.

No A*, a fila de prioridade deve utilizar `f(n) = g(n) + h(n)`, e não apenas a distância acumulada guardada no estado.

### 7.2. CSP

Formular o problema como um Problema de Satisfação de Restrições:

- Utilizar a biblioteca python constaints
- Identificar variáveis.
- Definir os domínios.
- Definir as restrições.
- Implementar a atribuição de veículos e pedidos.
- Apresentar uma solução viável e o número de backtracks.

### 7.3. Pesquisa local

Implementar Hill-Climbing a partir da solução obtida pelo Greedy e apresentar gráficos do custo ao longo das iterações.

### 7.4. Análise final

Comparar os algoritmos, apresentar tempos de execução, custos e soluções obtidas, e identificar possíveis melhorias futuras.

## 8. Como utilizar o model.py

Depois de colocar o ficheiro na pasta do projeto com o nome `model.py`, podemos importar as classes e funções para o notebook:

```python
from model import (
    Problem,
    State,
    Request,
    Vehicle,
    h_mais_distante,
    executar_testes_manuais
)
```

Para carregar o conjunto *small*:

```python
problem = Problem("docs/data_small_30_31oct2026/")
```

Para executar os testes manuais:

```python
executar_testes_manuais("docs/data_small_30_31oct2026/")
```

## 9. Resumo

Neste momento, temos duas componentes importantes desenvolvidas:

1. **EDA:** permite conhecer os dados, identificar as restrições e compreender a dimensão do problema.
2. **Modelação:** transforma os dados numa estrutura Python, disponibiliza funções de custo e validação e prepara a representação dos estados e a primeira heurística.

O `model.py` não procura ainda a melhor rota. É a infraestrutura que vai permitir aos algoritmos fazer essa pesquisa sem terem de voltar a implementar o carregamento dos dados, a consulta das distâncias ou a validação das restrições.

O próximo objetivo do grupo é utilizar esta base para implementar os algoritmos de pesquisa informada, começando pela geração dos estados sucessores e pela definição do estado inicial e do objetivo.

**Nota de integração:** ainda temos de validar a versão corrigida com os CSV reais e garantir, na geração dos sucessores, a atualização dos horários de chegada ao armazém. Também devemos assegurar que os itens de cada encomenda são entregues em conjunto, conforme a decisão de modelação documentada na EDA. A segunda heurística continua por desenvolver (?).

### Dica de ordem de desenvolvimento

1 - Terminar e validar o model.py e as heuristicas,
2 - Criar o estado inicial de cada veículo,
3 - Implementar a geração de ações possíveis (sucessores),
4 - Definir quando uma rota está concluída,
5 - Implementar Greedy com duas heurísticas,
6 - Implementar A* com as mesmas duas heurísticas,
7 - Comparar distâncias e nós expandidos,
8 - Implementar o CSP com python-constraint,
9 - Implementar Hill-Climbing a partir do Greedy,
10 - Analisar os resultados
