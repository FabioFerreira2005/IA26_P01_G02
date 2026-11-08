"""CSP para atribuir encomendas completas a veículos.

O modelo usa uma variável por encomenda. O domínio contém os veículos que
conseguem transportar a encomenda inteira e para os quais existe, isoladamente,
uma sequência temporal viável de recolhas, armazém e entrega.

Há dois âmbitos de capacidade:
* ``single_load``: o peso total atribuído a um veículo não pode exceder a sua
  capacidade. É a interpretação clássica do CSP e é útil para comparar solvers.
* ``multi_trip``: cada encomenda tem de caber numa viagem, mas o total atribuído
  pode exceder a capacidade, pois o veículo pode regressar ao armazém entre
  viagens. Este modo é compatível com o fluxo representado em ``model.py``.

O balanceamento de carga é uma heurística suave: ordena os valores do domínio
para preferir a atribuição com menor diferença de carga normalizada. Não rejeita
soluções por estarem desequilibradas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class OrderTask:
    """Encomenda completa que será atribuída como uma unidade."""

    order_id: int
    item_ids: Tuple[int, ...]
    weight_kg: float
    earliest_deadline: datetime


@dataclass
class CSPResult:
    """Resultado comum aos três métodos de resolução."""

    method: str
    feasible: bool
    assignment: Dict[int, int]
    loads_kg: Dict[int, float]
    balance_score: Optional[float]
    backtracks: int = 0
    nodes: int = 0
    solutions_examined: int = 0
    optimal_balance_proven: bool = False
    capacity_mode: str = "single_load"
    message: str = ""


def _as_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _planning_start(problem, tasks: Sequence[OrderTask], supplied: Optional[datetime]) -> datetime:
    if supplied is not None:
        return supplied
    rules = getattr(problem, "regras", {})
    start_date = _as_datetime(rules.get("start_date")) if isinstance(rules, Mapping) else None
    if start_date is not None:
        return datetime.combine(start_date.date(), time.min)
    return min(
        problem.pedidos[item_id].availability_start
        for task in tasks
        for item_id in task.item_ids
    )


def _temporalmente_viavel_isolada(problem, task: OrderTask, start: datetime) -> bool:
    """Verifica se uma encomenda é viável quando planeada sozinha.

    Procura uma ordem de visita aos produtores através de programação dinâmica
    sobre subconjuntos. Esta verificação não substitui o verificador de rotas:
    não considera conflitos com outras encomendas atribuídas ao mesmo veículo.
    """
    requests = [problem.pedidos[item_id] for item_id in task.item_ids]
    by_pickup: Dict[int, List[object]] = {}
    for req in requests:
        by_pickup.setdefault(req.pickup_loc, []).append(req)
    locations = tuple(sorted(by_pickup))
    if not locations:
        return False

    n = len(locations)
    full = (1 << n) - 1
    # (máscara, última paragem) -> hora de fim de serviço mais cedo.
    earliest_finish: Dict[Tuple[int, int], datetime] = {}
    warehouse = problem.armazem
    stop_service = timedelta(minutes=problem.tempo_servico_min)

    def visitar(mask: int, previous_loc: int, previous_time: datetime, next_index: int):
        loc = locations[next_index]
        arrival = previous_time + timedelta(minutes=problem.tempo_entre(previous_loc, loc))
        at_location = by_pickup[loc]
        service_start = max([arrival] + [req.availability_start for req in at_location])
        if any(service_start > req.availability_end for req in at_location):
            return None
        return service_start + stop_service

    for index in range(n):
        finish = visitar(0, warehouse, start, index)
        if finish is not None:
            earliest_finish[(1 << index, index)] = finish

    for mask in range(1, full + 1):
        for last in range(n):
            current = earliest_finish.get((mask, last))
            if current is None:
                continue
            for nxt in range(n):
                bit = 1 << nxt
                if mask & bit:
                    continue
                finish = visitar(mask, locations[last], current, nxt)
                if finish is None:
                    continue
                key = (mask | bit, nxt)
                if key not in earliest_finish or finish < earliest_finish[key]:
                    earliest_finish[key] = finish

    for last in range(n):
        finish_pickups = earliest_finish.get((full, last))
        if finish_pickups is None:
            continue
        arrival_warehouse = finish_pickups + timedelta(
            minutes=problem.tempo_entre(locations[last], warehouse)
        )
        start_loading = arrival_warehouse + timedelta(minutes=problem.tempo_armazem_min)
        if (start_loading - arrival_warehouse).total_seconds() / 3600 > problem.permanencia_max_h + 1e-9:
            continue
        departure_delivery = start_loading + timedelta(minutes=problem.tempo_armazem_min)
        delivery_loc = requests[0].delivery_loc
        arrival_delivery = departure_delivery + timedelta(
            minutes=problem.tempo_entre(warehouse, delivery_loc)
        )
        delivery_start = max([arrival_delivery] + [req.delivery_start for req in requests])
        if all(delivery_start <= req.delivery_end for req in requests):
            return True
    return False


class FleetCSP:
    """Constrói e resolve a CSP de atribuição de encomendas a veículos.

    Args:
        problem: instância ``Problem`` carregada por ``model.py``.
        item_ids: itens a planear. Cada encomenda incluída tem de estar completa.
        vehicle_ids: veículos disponíveis; por omissão usa toda a frota.
        planning_start: início do horizonte temporal. Por omissão usa
            ``rules.start_date`` à meia-noite, ou a primeira disponibilidade.
    """

    CAPACITY_MODES = {"single_load", "multi_trip"}

    def __init__(
        self,
        problem,
        item_ids: Optional[Iterable[int]] = None,
        vehicle_ids: Optional[Iterable[int]] = None,
        planning_start: Optional[datetime] = None,
    ):
        self.problem = problem
        selected_vehicles = problem.veiculos.keys() if vehicle_ids is None else vehicle_ids
        self.vehicle_ids = tuple(sorted(selected_vehicles))
        if not self.vehicle_ids:
            raise ValueError("A frota não pode estar vazia.")
        unknown_vehicles = set(self.vehicle_ids).difference(problem.veiculos)
        if unknown_vehicles:
            raise KeyError(f"Veículos desconhecidos: {sorted(unknown_vehicles)}")

        chosen_items = set(problem.pedidos if item_ids is None else item_ids)
        unknown_items = chosen_items.difference(problem.pedidos)
        if unknown_items:
            raise KeyError(f"Itens desconhecidos: {sorted(unknown_items)}")
        if not chosen_items:
            raise ValueError("A CSP necessita de pelo menos um item.")

        grouped: Dict[int, List[int]] = {}
        for item_id in sorted(chosen_items):
            req = problem.pedidos[item_id]
            grouped.setdefault(req.order_id, []).append(item_id)

        all_order_items: Dict[int, Set[int]] = {}
        for req in problem.pedidos.values():
            all_order_items.setdefault(req.order_id, set()).add(req.item_id)

        for order_id, ids in grouped.items():
            if set(ids) != all_order_items[order_id]:
                missing = sorted(all_order_items[order_id].difference(ids))
                raise ValueError(
                    f"A encomenda {order_id} está incompleta; faltam os itens {missing}."
                )

        self.tasks = tuple(
            OrderTask(
                order_id=order_id,
                item_ids=tuple(ids),
                weight_kg=sum(problem.pedidos[i].weight_kg for i in ids),
                earliest_deadline=min(problem.pedidos[i].delivery_end for i in ids),
            )
            for order_id, ids in sorted(grouped.items())
        )
        self.planning_start = _planning_start(problem, self.tasks, planning_start)
        self.domains: Dict[int, Tuple[int, ...]] = {}
        self.domain_reasons: Dict[int, Dict[int, Tuple[str, ...]]] = {}
        self._build_domains()
        empty = [task.order_id for task in self.tasks if not self.domains[task.order_id]]
        if empty:
            details = {
                order_id: self.domain_reasons[order_id]
                for order_id in empty
            }
            raise ValueError(
                "Não há veículos compatíveis para as encomendas "
                f"{empty}. Motivos por veículo: {details}"
            )

    def _build_domains(self) -> None:
        for task in self.tasks:
            eligible: List[int] = []
            reasons: Dict[int, Tuple[str, ...]] = {}
            for vehicle_id in self.vehicle_ids:
                vehicle = self.problem.veiculos[vehicle_id]
                why: List[str] = []
                if task.weight_kg > vehicle.capacity_kg + 1e-6:
                    why.append("peso da encomenda excede a capacidade do veículo")

                # O dataset atual não define requisitos de refrigeração por
                # produto. Se esse atributo for adicionado, passa a restringir
                # automaticamente os domínios sem inferir pela categoria.
                requires_cold = any(
                    bool(getattr(self.problem.pedidos[i], "requires_refrigeration", False))
                    for i in task.item_ids
                )
                if requires_cold and not vehicle.refrigerated:
                    why.append("a encomenda requer refrigeração")

                if not _temporalmente_viavel_isolada(self.problem, task, self.planning_start):
                    why.append("janelas temporais inviáveis mesmo com a encomenda isolada")

                reasons[vehicle_id] = tuple(why)
                if not why:
                    eligible.append(vehicle_id)
            self.domains[task.order_id] = tuple(eligible)
            self.domain_reasons[task.order_id] = reasons

    def _validate_mode(self, capacity_mode: str) -> str:
        mode = capacity_mode.strip().lower()
        if mode not in self.CAPACITY_MODES:
            raise ValueError("capacity_mode deve ser 'single_load' ou 'multi_trip'.")
        return mode

    def _loads(self, assignment: Mapping[int, int]) -> Dict[int, float]:
        loads = {vehicle_id: 0.0 for vehicle_id in self.vehicle_ids}
        task_by_order = {task.order_id: task for task in self.tasks}
        for order_id, vehicle_id in assignment.items():
            loads[vehicle_id] += task_by_order[order_id].weight_kg
        return loads

    def _balance_score(self, loads: Mapping[int, float]) -> float:
        ratios = [loads[vid] / self.problem.veiculos[vid].capacity_kg for vid in self.vehicle_ids]
        return max(ratios) - min(ratios)

    def _balanced_values(
        self, order_id: int, candidates: Sequence[int], loads: Mapping[int, float]
    ) -> List[int]:
        task = next(t for t in self.tasks if t.order_id == order_id)

        def projected_score(vehicle_id: int) -> Tuple[float, int]:
            after = dict(loads)
            after[vehicle_id] += task.weight_kg
            return self._balance_score(after), vehicle_id

        return sorted(candidates, key=projected_score)

    def _make_result(
        self,
        method: str,
        assignment: Optional[Dict[int, int]],
        capacity_mode: str,
        **stats,
    ) -> CSPResult:
        assignment = assignment or {}
        loads = self._loads(assignment)
        return CSPResult(
            method=method,
            feasible=len(assignment) == len(self.tasks),
            assignment=dict(assignment),
            loads_kg=loads,
            balance_score=self._balance_score(loads) if assignment else None,
            capacity_mode=capacity_mode,
            **stats,
        )

    def solve_backtracking(
        self,
        *,
        use_mrv: bool = True,
        capacity_mode: str = "single_load",
    ) -> CSPResult:
        """Resolve com backtracking próprio e ordenação heurística balanceada.

        ``use_mrv=True`` escolhe dinamicamente a variável com menos valores
        ainda possíveis (MRV). ``backtracks`` conta os ramos que foram
        abandonados porque não conduziam a uma atribuição completa.
        """
        mode = self._validate_mode(capacity_mode)
        assignment: Dict[int, int] = {}
        loads = {vid: 0.0 for vid in self.vehicle_ids}
        task_map = {task.order_id: task for task in self.tasks}
        nodes = 0
        backtracks = 0

        def remaining_candidates(order_id: int) -> List[int]:
            candidates = list(self.domains[order_id])
            if mode == "single_load":
                candidates = [
                    vid for vid in candidates
                    if loads[vid] + task_map[order_id].weight_kg
                    <= self.problem.veiculos[vid].capacity_kg + 1e-6
                ]
            return candidates

        def capacity_bound_ok(unassigned: Sequence[int]) -> bool:
            if mode != "single_load":
                return True
            remaining_weight = sum(task_map[oid].weight_kg for oid in unassigned)
            residual_capacity = sum(
                max(0.0, self.problem.veiculos[vid].capacity_kg - loads[vid])
                for vid in self.vehicle_ids
            )
            return remaining_weight <= residual_capacity + 1e-6

        def rec(unassigned: Tuple[int, ...]) -> bool:
            nonlocal nodes, backtracks
            nodes += 1
            if not unassigned:
                return True
            if not capacity_bound_ok(unassigned):
                backtracks += 1
                return False

            candidate_map = {oid: remaining_candidates(oid) for oid in unassigned}
            if use_mrv:
                order_id = min(
                    unassigned,
                    key=lambda oid: (
                        len(candidate_map[oid]),
                        -task_map[oid].weight_kg,
                        task_map[oid].earliest_deadline,
                        oid,
                    ),
                )
            else:
                order_id = min(unassigned)

            candidates = self._balanced_values(order_id, candidate_map[order_id], loads)
            if not candidates:
                backtracks += 1
                return False

            next_unassigned = tuple(oid for oid in unassigned if oid != order_id)
            for vehicle_id in candidates:
                task = task_map[order_id]
                assignment[order_id] = vehicle_id
                loads[vehicle_id] += task.weight_kg
                if rec(next_unassigned):
                    return True
                loads[vehicle_id] -= task.weight_kg
                del assignment[order_id]
                backtracks += 1
            return False

        found = rec(tuple(task.order_id for task in self.tasks))
        return self._make_result(
            "backtracking_mrv" if use_mrv else "backtracking_sem_mrv",
            assignment if found else None,
            mode,
            backtracks=backtracks,
            nodes=nodes,
            message=(
                "Atribuição encontrada; o balanceamento foi usado para ordenar escolhas."
                if found else "Não existe atribuição viável com as restrições selecionadas."
            ),
        )

    def solve_python_constraint(
        self,
        *,
        capacity_mode: str = "single_load",
        max_solutions: Optional[int] = 10_000,
    ) -> CSPResult:
        """Resolve com ``python-constraint`` e escolhe a solução mais equilibrada.

        A iteração pode ser limitada por ``max_solutions``; o resultado indica
        se todas as soluções foram enumeradas, logo se o melhor balanceamento é
        ótimo entre as atribuições enumeradas.
        """
        mode = self._validate_mode(capacity_mode)
        if max_solutions is not None and max_solutions < 1:
            raise ValueError("max_solutions deve ser >= 1 ou None.")
        try:
            from constraint import Problem as ConstraintProblem
        except ImportError as exc:
            raise ImportError(
                "Instala as dependências do projeto (`pip install -r requirements.txt`) "
                "para usar python-constraint."
            ) from exc

        csp = ConstraintProblem()
        ordered_tasks = sorted(
            self.tasks,
            key=lambda task: (len(self.domains[task.order_id]), -task.weight_kg, task.order_id),
        )
        variables = [task.order_id for task in ordered_tasks]
        task_map = {task.order_id: task for task in self.tasks}
        for task in ordered_tasks:
            oid = task.order_id
            csp.addVariable(oid, list(self.domains[oid]))
            domain = set(self.domains[oid])
            csp.addConstraint(lambda vehicle_id, allowed=domain: vehicle_id in allowed, (oid,))

        if mode == "single_load":
            capacities = {vid: self.problem.veiculos[vid].capacity_kg for vid in self.vehicle_ids}

            def capacity_constraint(*values):
                loads = {vid: 0.0 for vid in self.vehicle_ids}
                for oid, vid in zip(variables, values):
                    loads[vid] += task_map[oid].weight_kg
                return all(loads[vid] <= capacities[vid] + 1e-6 for vid in self.vehicle_ids)

            csp.addConstraint(capacity_constraint, variables)

        best: Optional[Dict[int, int]] = None
        best_score = float("inf")
        count = 0
        exhausted = True
        for solution in csp.getSolutionIter():
            count += 1
            score = self._balance_score(self._loads(solution))
            if score < best_score:
                best, best_score = dict(solution), score
            if max_solutions is not None and count >= max_solutions:
                exhausted = False
                break

        return self._make_result(
            "python_constraint",
            best,
            mode,
            solutions_examined=count,
            optimal_balance_proven=bool(best is not None and exhausted),
            message=(
                "A melhor solução equilibrada foi encontrada em todas as soluções."
                if best is not None and exhausted else
                "Melhor solução entre as atribuições enumeradas; a enumeração foi limitada."
                if best is not None else
                "Não existe atribuição viável com as restrições selecionadas."
            ),
        )

    def summary_rows(self, result: CSPResult) -> List[Dict[str, object]]:
        """Devolve linhas simples para apresentação no notebook."""
        tasks = {task.order_id: task for task in self.tasks}
        return [
            {
                "order_id": task.order_id,
                "vehicle_id": result.assignment.get(task.order_id),
                "item_ids": list(task.item_ids),
                "weight_kg": round(task.weight_kg, 2),
                "eligible_vehicles": list(self.domains[task.order_id]),
            }
            for task in self.tasks
        ]


def compare_backtracking(
    csp: FleetCSP,
    *,
    capacity_mode: str = "single_load",
) -> List[CSPResult]:
    """Compara backtracking estático e MRV com a mesma heurística de valores."""
    return [
        csp.solve_backtracking(use_mrv=False, capacity_mode=capacity_mode),
        csp.solve_backtracking(use_mrv=True, capacity_mode=capacity_mode),
    ]

