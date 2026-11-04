"""
heuristicas.py — Heurísticas admissíveis para o Greedy e o A*.

IA 2026/27 · TP1 · Grupo 02 (IA26_P01_G02)

Todas as heurísticas recebem (state, sub):
  - state: model.State (estado da pesquisa);
  - sub:   pesquisa.Subproblema (um veículo num dia: o que tem de recolher e entregar).

Todas usam problem.distancia_minima (Floyd-Warshall, ver model.py), que nunca é
maior do que a distância real entre duas paragens. É isto que garante que nenhuma
heurística sobrestima o custo que falta (admissibilidade).

Heurísticas oficiais do grupo:
  - H1 h_pedido_mais_caro  — percurso obrigatório do item mais caro (máximo, nunca soma);
  - H2 h_mst               — árvore geradora mínima das paragens pendentes (versão melhorada).
Referências para comparação:
  - UCS  h_zero            — sem heurística (A* com h=0 é o UCS);
  - Ref. h_mais_distante   — paragem pendente mais distante (ideia do Fábio, adaptada ao dia);
  - max(H1, H2)            — combinação das duas oficiais, também admissível.
"""

from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------
# Percurso obrigatório que ainda falta a cada item
# ---------------------------------------------------------------------

def percurso_restante_item(state, sub, item_id: int) -> Optional[List[int]]:
    """
    Devolve a sequência de paragens que o item ainda obriga o veículo a visitar
    (por esta ordem) até ao fim do dia, ou None se o item já não exige nada hoje.

    O fluxo é sempre produtor -> armazém -> cliente e o dia acaba no armazém.
    Itens recolhidos hoje mas só entregues amanhã acabam o dia no armazém.
    """
    pb = sub.problem
    A = pb.armazem
    req = pb.pedidos[item_id]
    entrega_hoje = item_id in sub.entregar

    if item_id in state.entregues:
        return None
    if item_id in state.para_entrega_a_bordo:          # já carregado: falta entregar
        return [req.delivery_loc, A]
    if item_id in state.recolhidos_a_bordo:            # recolhido: falta descarregar
        return [A, req.delivery_loc, A] if entrega_hoje else [A]
    if item_id in state.no_armazem:                    # no armazém
        return [A, req.delivery_loc, A] if entrega_hoje else None
    # ainda não recolhido
    return [req.pickup_loc, A, req.delivery_loc, A] if entrega_hoje else [req.pickup_loc, A]


def itens_do_dia(sub) -> Set[int]:
    """Todos os itens que o subproblema envolve (recolher e/ou entregar hoje)."""
    return set(sub.recolher) | set(sub.entregar)


def paragens_pendentes(state, sub) -> Set[int]:
    """União das paragens que ainda falta visitar (versão do State.paragens_pendentes que sabe o dia)."""
    pendentes: Set[int] = set()
    for iid in itens_do_dia(sub):
        seq = percurso_restante_item(state, sub, iid)
        if seq:
            pendentes.update(seq)
    return pendentes


# ---------------------------------------------------------------------
# UCS — sem heurística
# ---------------------------------------------------------------------

def h_zero(state, sub) -> float:
    """h = 0. O A* com esta heurística é exatamente o UCS."""
    return 0.0


# ---------------------------------------------------------------------
# Ref. — paragem pendente mais distante (referência)
# ---------------------------------------------------------------------

def h_mais_distante(state, sub) -> float:
    """
    h = max_p [ d(atual, p) + d(p, armazém) ] para cada paragem pendente p.
    Admissível: qualquer rota tem de passar por p e acabar no armazém.
    (Mesma ideia do h_mais_distante do model.py, mas sabe que os itens
    entregues amanhã só têm de chegar hoje ao armazém.)
    """
    d = sub.problem.distancia_minima
    A = sub.problem.armazem
    atual = state.paragem_atual
    pendentes = paragens_pendentes(state, sub)
    if not pendentes:
        return d[(atual, A)]
    return max(d[(atual, p)] + d[(p, A)] for p in pendentes)


# ---------------------------------------------------------------------
# H1 — pedido mais caro (heurística oficial 1)
# ---------------------------------------------------------------------

def h_pedido_mais_caro(state, sub) -> float:
    """
    Para cada item, soma as distâncias do percurso que ele ainda obriga a fazer:
        atual -> [produtor] -> armazém -> [cliente] -> armazém
    e devolve o MÁXIMO entre os itens.

    Admissível: a rota real tem de visitar as paragens de cada item por esta
    ordem, por isso nunca é mais curta do que o percurso de um único item.
    Atenção: SOMAR os itens já não é admissível, porque uma mesma viagem
    serve vários itens ao mesmo tempo.
    """
    d = sub.problem.distancia_minima
    A = sub.problem.armazem
    atual = state.paragem_atual
    melhor = d[(atual, A)]                 # no mínimo, voltar ao armazém
    for iid in itens_do_dia(sub):
        seq = percurso_restante_item(state, sub, iid)
        if not seq:
            continue
        custo = d[(atual, seq[0])]
        for a, b in zip(seq[:-1], seq[1:]):
            custo += d[(a, b)]
        if custo > melhor:
            melhor = custo
    return melhor


# ---------------------------------------------------------------------
# H2 — árvore geradora mínima (heurística oficial 2)
# ---------------------------------------------------------------------

def peso_mst(nos: List[int], d: Dict) -> float:
    """
    Peso da árvore geradora mínima (algoritmo de Prim) dos nós dados.
    Usa um dicionário de distâncias em vez do pandas, porque é chamada
    milhares de vezes durante a pesquisa. Distâncias 0 entre paragens
    diferentes (paragens no mesmo sítio) são ligações válidas.
    """
    nos = list(dict.fromkeys(nos))
    if len(nos) <= 1:
        return 0.0
    dentro = {nos[0]}
    custo_ligar = {n: d[(nos[0], n)] for n in nos[1:]}
    total = 0.0
    while custo_ligar:
        n = min(custo_ligar, key=custo_ligar.get)
        total += custo_ligar.pop(n)
        dentro.add(n)
        for m in custo_ligar:
            if d[(n, m)] < custo_ligar[m]:
                custo_ligar[m] = d[(n, m)]
    return total


def h_mst(state, sub) -> float:
    """
    h = min_p d(atual, p) + MST(paragens pendentes) + min_p d(p, armazém)

    Admissível: a rota que falta sai da posição atual para uma primeira paragem
    pendente (>= min d(atual, p)), percorre todas as pendentes (>= MST, porque
    qualquer caminho que liga todos os nós custa pelo menos a MST) e, da última,
    volta ao armazém (>= min d(p, armazém)).
    """
    d = sub.problem.distancia_minima
    A = sub.problem.armazem
    atual = state.paragem_atual
    pendentes = paragens_pendentes(state, sub)
    if not pendentes:
        return d[(atual, A)]
    entrada = min(d[(atual, p)] for p in pendentes)
    saida = min(d[(p, A)] for p in pendentes)
    return entrada + peso_mst(sorted(pendentes), d) + saida


# ---------------------------------------------------------------------
# max(H1, H2) — combinação das duas oficiais
# ---------------------------------------------------------------------

def h_max_h1_h2(state, sub) -> float:
    """max(H1, H2): o máximo de heurísticas admissíveis continua admissível."""
    return max(h_pedido_mais_caro(state, sub), h_mst(state, sub))


HEURISTICAS = {
    "H1 (pedido mais caro)": h_pedido_mais_caro,
    "H2 (MST)": h_mst,
    "Ref. (mais distante)": h_mais_distante,
    "max(H1, H2)": h_max_h1_h2,
}
