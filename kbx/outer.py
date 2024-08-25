from __future__ import annotations

from dataclasses import dataclass
from typing import final, Any, Iterable

from pyk.kast import KAtt
from pyk.kast.att import EMPTY_ATT
from pyk.kast.inner import KInner, KApply, KVariable, KLabel, KToken, KRewrite, top_down
from pyk.kast.outer import KSentence, KProduction, KSort, KTerminal, Atts, KNonTerminal, KDefinition
from pyk.kast.rewrite import indexed_rewrite
from pyk.utils import single


def get_pure_k_definition(k_definition: KDefinition) -> KDefinition:
    uni_pure_k_def = KDefinition(
        main_module_name=k_definition.main_module_name,
        all_modules=tuple(m for m in k_definition.all_modules
                          if '/include/kframework/builtin/' not in str(m.att[Atts.SOURCE])),
        requires=k_definition.requires,
        att=k_definition.att
    )
    return uni_pure_k_def


def is_from_single_file(k_definition: KDefinition) -> bool:
    unique_sources = {m.att[Atts.SOURCE] for m in k_definition.all_modules}
    return len(unique_sources) == 1


@final
@dataclass(frozen=True)
class KProductionsWithPriority(KSentence):
    priorities: tuple[tuple[KProduction], ...]
    att: KAtt

    def __init__(self, priorities: Iterable[Iterable[KProduction]] = (),  att: KAtt = EMPTY_ATT):
        object.__setattr__(self, 'priorities', tuple(tuple(group) for group in priorities))
        object.__setattr__(self, 'att', att)

    def let_att(self, att: KAtt) -> KProductionsWithPriority:
        return KProductionsWithPriority(self.priorities, att)

    def to_dict(self) -> dict[str, Any]:
        pass


@final
@dataclass(frozen=True)
class KProductionList(KSentence):
    sort: KSort
    content_sort: KSort
    link_terminal: KTerminal
    att: KAtt

    def __init__(
            self,
            sort: str | KSort,
            content_sort: str | KSort,
            link_terminal: str | KTerminal,
            att: KAtt = EMPTY_ATT,
    ):
        if isinstance(sort, str):
            sort = KSort(sort)
        if isinstance(content_sort, str):
            content_sort = KSort(content_sort)
        if isinstance(link_terminal, str):
            link_terminal = KTerminal(link_terminal)
        object.__setattr__(self, 'sort', sort)
        object.__setattr__(self, 'content_sort', content_sort)
        object.__setattr__(self, 'link_terminal', link_terminal)
        object.__setattr__(self, 'att', att)

    @staticmethod
    def from_kproduction(
            production: KProduction,
    ):
        assert production.att.get(Atts.USER_LIST), f"Expected the production to be a user list, but found {production.att.get(Atts.USER_LIST)}"
        att = production.att.discard([Atts.USER_LIST])
        assert len(production.items) == 3, f"Expected 3 items in the production, but found {len(production.items)}"
        content_sort_container = production.items[0]
        assert isinstance(content_sort_container, KNonTerminal), f"Expected the first item to be a KNonTerminal, but found {type(content_sort_container)}"
        content_sort = content_sort_container.sort
        link_terminal = production.items[1]
        assert isinstance(link_terminal, KTerminal), f"Expected the second item to be a KTerminal, but found {type(link_terminal)}"
        return KProductionList(production.sort, content_sort, link_terminal, att)

    def pretty_print(self) -> str:
        return f"syntax {self.sort.name} ::= List{{{self.content_sort.name}, \"{self.link_terminal.value}\"}}"

    def let_att(self, att: KAtt) -> KProductionList:
        return KProductionList(self.sort, self.content_sort, self.link_terminal, att)

    def to_dict(self) -> dict[str, Any]:
        pass


@final
@dataclass(frozen=True)
class KConfiguration(KSentence):
    cell_name: str
    content: KInner | tuple[KConfiguration, ...]
    multiplicity: str | None
    multi_type: str | None
    att: KAtt

    def __init__(self,
                 cell_name: str,
                 content: KInner | Iterable[KConfiguration] = (),
                 multiplicity: str | None = None,
                 multi_type: str | None = None,
                 att: KAtt = EMPTY_ATT):
        object.__setattr__(self, 'cell_name', cell_name)
        object.__setattr__(self, 'content', content)
        object.__setattr__(self, 'multiplicity', multiplicity)
        object.__setattr__(self, 'multi_type', multi_type)
        object.__setattr__(self, 'att', att)

    def let_att(self, att: KAtt) -> KConfiguration:
        return KConfiguration(self.cell_name, self.content, self.multiplicity, self.multi_type, att)

    def to_dict(self) -> dict[str, Any]:
        pass


    @staticmethod
    def from_kinner(
            init_config: KInner,
            multi_cells: dict[str, tuple[KProduction, str, str]],
            # cell_name: tuple(init_config, sort.name, multiplicity, type)
            kdefinition: KDefinition
    ) -> KConfiguration:
        assert isinstance(init_config, KApply), f"Expected the inner to be a KApply, but found {type(init_config)}"
        assert init_config.is_cell, f"Expected the inner to be a cell, but found {init_config.is_cell}"
        cell_name = init_config.label.name[1:-1]
        content_org = init_config.args[1]
        multiplicity = None
        _type = None
        if cell_name in multi_cells:
            multiplicity, _type = multi_cells[cell_name][1:]
        if isinstance(content_org, KApply) and content_org.label.name == "#cells":
            content = []
            for cell in content_org.args:
                content.append(KConfiguration.from_kinner(cell, multi_cells, kdefinition))
            if len(content) == 0:
                cell_sort = cell_name_to_sort_name(cell_name)
                cell_prod = single(prod for prod in kdefinition.syntax_productions
                                   if prod.sort == KSort(cell_sort) and Atts.CELL in prod.att)
                child_sort = single(cell_prod.argument_sorts)
                child_config = kdefinition.init_config(child_sort)
                child_config = KConfiguration.from_kinner(child_config, multi_cells, kdefinition)
                return KConfiguration(cell_name, (child_config,), multiplicity, _type)
            return KConfiguration(cell_name, tuple(content), multiplicity, _type)
        return KConfiguration(cell_name, content_org, multiplicity, _type)


def cell_name_to_sort_name(cell_name: str) -> str:
    # a-b-c -> ABCCell
    return ''.join([word.capitalize() for word in cell_name.split('-')]) + 'Cell'


