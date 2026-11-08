# IA26_P01_G02 — Agente de routing para distribuição de produtos locais

Repositório do 1º Trabalho Prático de **Inteligência Artificial** (2026/27) — Licenciatura em Engenharia de Sistemas Informáticos, UPCA.

**Tema:** *Local food*. Um agente de routing planeia a recolha e a entrega para uma plataforma que liga pequenos produtores locais, clientes e centros de recolha no distrito de Braga.

## Grupo 02

| Nome | Nº de aluno |
|---|---|
| André Rodrigues | 26900 |
| Tiago Gonçalves | 29389 |
| Fábio Ferreira | 29365 |
| Alexandre Silva | 29382 |

Repositorio GitHub: https://github.com/FabioFerreira2005/IA26_P01_G02

## Objetivo

Encontrar rotas de recolha (nos produtores) e de entrega (no local escolhido por cada cliente) que **minimizem os quilómetros**, respeitando:
- as janelas temporais;
- a capacidade dos veículos;
- o fluxo obrigatório produtor → armazém → cliente;
- as 24 h máximas no armazém.

Técnicas usadas: **pesquisa informada** (Greedy e A\* com 2 heurísticas, UCS como referência), **pesquisa local** (Hill-Climbing) e **CSP** (python-constraint).

## Entregáveis do enunciado → onde estão

| O guia pede | Ficheiro |
|---|---|
| Introdução (contexto, grupo) | `IA26_P01_G02.ipynb`, secção 1 |
| EDA — *Deliverable: 01_eda_tiny.ipynb* | `01_eda_tiny.ipynb` (resumo na secção 2 do notebook principal) |
| Modelação — *model.py + tests with hand-written routes* | `model.py` e `testes_modelo.py` (resumo na secção 3) |
| Pesquisa informada — Greedy e A\* com 2 heurísticas, nós expandidos | `IA26_P01_G02.ipynb`, secção 4.1 |
| CSP — *feasible assignment and number of backtracks* | `IA26_P01_G02.ipynb`, secção 4.2 |
| Pesquisa informada — *routes for the 2 tiny vehicles* | `IA26_P01_G02.ipynb`, secção 4.3 |
| Pesquisa local — *cost vs. iteration curves* | `IA26_P01_G02.ipynb`, secção 4.4 |
| Análise de resultados e conclusão | `IA26_P01_G02.ipynb`, secções 5 e 6 |
| *Code and documentation merged into a Jupyter Notebook* | **`IA26_P01_G02.ipynb`**: todo o código da resolução está no notebook, junto do texto |
| *readme.txt with the link to the repository* | `readme.txt` |
| *Other files needed to run the notebook* | `model.py`, `docs/`, `requirements.txt` |

## Estrutura

```
IA26_P01_G02/
├── IA26_P01_G02.ipynb          # NOTEBOOK PRINCIPAL (tiny): introdução, EDA, modelação, CÓDIGO da resolução, resultados, conclusão
├── IA26_P01_G02_small.ipynb    # O mesmo notebook para o conjunto small (só muda a linha PASTA)
├── 01_eda_tiny.ipynb           # EDA completa do tiny (entregável da 1.ª fase)
├── 01_eda_small.ipynb          # EDA do small (mesmo código)
├── model.py                    # Modelação: Problem, Request, Vehicle, State, leitura dos CSVs, custo, verificadores
├── testes_modelo.py            # 11 testes do model.py com rotas escritas à mão (py testes_modelo.py)
├── requirements.txt            # Dependências (versões fixas)
├── readme.txt                  # Link do repositório (vai no ZIP do Moodle)
├── README.md                   # Este ficheiro
└── docs/
    ├── IA91_Project01_Guide.pdf    # Enunciado
    ├── data_tiny/                  # Conjunto pequeno (12 encomendas)
    └── data_small_30_31oct2026/    # Conjunto maior (25 encomendas)
```

**Como as partes se ligam** (todas as secções da 4 estão no notebook):

```
docs/*.csv ─► model.py ─► 4.1 pesquisa ─► 4.2 CSP ─► 4.3 rotas dos 2 veículos ─► model.py (verificador) ─► 4.4 Hill-Climbing
  (dados)     Problem     heurísticas,     quem faz     A* para cada veículo        confirma as regras          melhora o Greedy
                          UCS/Greedy/A*    cada tarefa  e cada dia
```

A ordem do guia (pesquisa informada → pesquisa local → CSP) foi adaptada, como o guia permite (*"can be adapted"*): o CSP precisa da pesquisa para saber se há rota, as rotas dos 2 veículos precisam da divisão do CSP, e o Hill-Climbing precisa das rotas do Greedy.

## Opções para desenvolver o projeto (resumo)

Cada secção do notebook tem uma tabela **"Opções consideradas"**. As principais:

| Parte | Opções | Escolhida | Porquê |
|---|---|---|---|
| Custo | km · tempo · os dois | **km** | O tempo entra como restrição (janelas) |
| Dois dias | um problema único · dia a dia | **dia a dia** | Só se ligam pelos itens que dormem no armazém |
| Divisão das encomendas | por encomenda · por item · por **tarefa** | **tarefa**: `C` (mesmo dia), `R-P` (recolha por produtor), `E` (entrega) | O armazém permite que veículos diferentes recolham partes da mesma encomenda do dia seguinte |
| Heurísticas | linha reta · paragem mais distante · **h1** · **h2** · max(h1, h2) · urgência | **só h1** (pedido mais caro) **e h2** (árvore mínima) | Admissíveis e com visões diferentes (um item vs o conjunto). A linha reta é redundante (matriz ÷ 1,3), a paragem mais distante foi o ponto de partida que a h1 substitui, e o max ganha pouco à h1 |
| Algoritmos de pesquisa | UCS · Greedy · A\* · Weighted A\* · IDA\* | **UCS, Greedy, A\*** | O guia pede Greedy e A\*; a UCS prova o ótimo |
| Pesquisa local | HC · Simulated Annealing · Tabu | **HC** sobre o Greedy, com **melhor vizinho** e **primeira melhoria** | Pedido pelo guia; movimentos trocar, mover, inverter e **mover bloco** (contributo do Alexandre) |
| CSP: variáveis e domínio | encomendas · itens · tarefas / veículo · (veículo, ordem) | **tarefas / veículo** | A ordem é trabalho da pesquisa; o CSP fica pequeno |
| CSP: janelas | horas como variáveis · verificar com A\* | **"existe rota" verificado com o A\*** | Liga o CSP à pesquisa sem milhares de variáveis |
| CSP: capacidade | total do dia · por viagem | **por viagem** (cada tarefa cabe no veículo; a carga ao longo da rota é verificada pelo A\*) | O veículo pode voltar ao armazém várias vezes (contributo do Fábio) |
| CSP: restrição suave | penalização · heurística | **heurística S1 (menos km)** + MRV | É o que o guia pede; o MRV reduz os backtracks |

## Resultados

| Conjunto | Encomendas | Melhor solução | A\* vs UCS (nós) | Hill-Climbing | Backtracks |
|---|---|---|---|---|---|
| tiny | **12 de 12** | **561,3 km** | A\* h1: 471 vs 978 | chega ao ótimo a partir do Greedy | 0 |
| small | **24 de 25** | **879,45 km** | A\* h1: 6477 vs 7664 | chega ao valor do A\* (com o mover bloco) | dia 30 impossível com 2 veículos: provado com 10 backtracks (MRV) contra 268 (ordem fixa); a encomenda 9 fica adiada |


## Contributos dos colegas integrados

Do trabalho que o Fábio e o Alexandre puseram no repositório (`pesquisa_informada/`, `pesquisa_local/`, `Auxiliares_dev_EDA/pesquisa_informada_prototipo/`), entrou nesta versão:

| De quem | Ideia | Onde entrou | Efeito |
|---|---|---|---|
| Fábio | O veículo pode voltar ao armazém várias vezes: a capacidade limita **cada viagem**, não o total do dia | CSP, restrições R1 e R2 (secção 4.2) | No small, o total baixou de 896,8 para **879,45 km** |
| Tiago | As heurísticas h1 e h2 como as duas oficiais | Secção 4.1 | Confirma a escolha; as extra (paragem mais distante e max) foram retiradas |
| Alexandre | Movimento **mover bloco** (or-opt) | Hill-Climbing (secção 4.4) | No small, é o movimento que tira o Greedy h1 do ótimo local (880,53 → 879,45 km) |
| Andre | Estratégia **primeira melhoria**, comparada com o melhor vizinho | Hill-Climbing (secção 4.4) | Chega ao mesmo resultado com menos avaliações |
| Alexandre | Resultado de referência do protótipo (small: 879,45 km) | Análise (secção 5) | O mesmo valor, obtido de outra forma, confirma a solução |

Ficaram de fora, por já estarem cobertos ou por acrescentarem complexidade: a função `otimizar_frota` do Fábio (o CSP faz essa divisão), o Simulated Annealing e as soluções baralhadas do Alexandre.

## Como executar

```powershell
py -m pip install -r requirements.txt
py testes_modelo.py          # 11 testes do model.py, poucos segundos
py -m notebook               # abrir IA26_P01_G02.ipynb → Kernel → Restart & Run All
```

**Tempos aproximados:**
- `IA26_P01_G02.ipynb` (tiny): cerca de 30 s;
- `IA26_P01_G02_small.ipynb`: cerca de 3 min, quase todos no CSP.

**Se algo correr mal:**
- **Correr os comandos dentro da pasta do projeto** (onde está este README). Se o Jupyter for aberto noutra pasta, aparece `FileNotFoundError: docs/...`.
- **No VS Code:** abrir a pasta do projeto, abrir o notebook e, em *Select Kernel* (canto superior direito), escolher o Python onde foram instaladas as bibliotecas (no Windows, o da pasta AppData).
- **`ModuleNotFoundError: No module named 'constraint'`** (ou `pandas`): o notebook está a usar outro Python. Correr outra vez `py -m pip install -r requirements.txt` ou escolher o kernel certo.

## Testes (`testes_modelo.py`)

São 11 testes com rotas escritas à mão, como pede o guia (*"model.py module + tests with hand-written routes"*). Para cada regra do enunciado (fluxo pelo armazém, janela de recolha, janela de entrega, capacidade e 24 h no armazém) há uma rota que a cumpre e outra que a viola, e o teste confirma que o verificador aceita uma e rejeita a outra pelo motivo certo. Também verificam a função de custo, uma solução com 2 veículos, uma solução com uma encomenda esquecida, a `chave()` do estado e a desigualdade triangular. Correm com `py testes_modelo.py` e devem dar **11 de 11**.

## Suposições 

| Pergunta | Suposição atual |
|---|---|
| A que horas saem os veículos? | 06:00 |
| Uma encomenda pode ser dividida entre veículos? | Entrega sempre inteira; a recolha de encomendas do dia seguinte divide-se por produtor |
| Várias viagens por veículo e por dia? | Sim, dentro da mesma rota (o veículo pode voltar ao armazém) |
| O veículo refrigerado é obrigatório para algum produto? | Não (não há regra no `rules.csv`) |
| Os 15 min no armazém são por visita? | Sim: 15 min para descarregar e 15 min para carregar, por visita |
| O custo é só a distância? | Sim (km); o tempo entra como restrição |
