from functools import partial

from pyk.kast import Atts, AttEntry
from pyk.kast.inner import KLabel, KApply, KInner, KVariable, KRewrite, KToken, bottom_up, KSort
from pyk.kast.outer import KRule, KImport, KDefinition
from pyk.prelude.collections import list_of, list_empty, map_item, MAP
from pyk.prelude.kbool import andBool, orBool
from kbx.outer import KConfiguration


COMPLEMENTS_CELL_NAME = 'kbx-complements-holder'
DEFAULT_COMPLEMENTS_VAR = KVariable('KbxComplements', 'Map')
GEN_VAR_NAME = 'KbxGenVar'
GEN_TODO_NAME = '?KbxGenTodo'
vars2todos_count = -1


def add_required_modules(kdef: KDefinition) -> KDefinition:
    """
    Add the required modules `MAP`, `LIST`, `INT-SYNTAX` to the K definition.
    """
    modules = kdef.all_modules_dict
    has_domains = False
    for module in modules.values():
        for import_module in module.imports:
            if import_module.name == 'DOMAINS':
                has_domains = True
    main_module = modules[kdef.main_module_name]
    if not has_domains:
        main_module = main_module.let(imports=[*main_module.imports, KImport('DOMAINS')])
    modules[kdef.main_module_name] = main_module
    return kdef.let(all_modules=[*modules.values()])


def vars2todos(rule: KRule, var_list: tuple[KInner, ...]) -> tuple[KRule, tuple[KInner, ...]]:
    body = rule.body
    requires = rule.requires
    ensures = rule.ensures
    todos = []

    def _curr_todo() -> KVariable:
        global vars2todos_count
        vars2todos_count += 1
        return KVariable(GEN_TODO_NAME + str(vars2todos_count))

    def _replace_var_with_todo(_token: KInner, to_replace: KVariable, replaced: KVariable) -> KInner:
        if isinstance(_token, KVariable) and _token.name == to_replace.name:
            return replaced
        return _token

    for var in var_list:
        todo = _curr_todo()
        todos.append(todo)
        replace_var_with_todo = partial(_replace_var_with_todo, to_replace=var, replaced=todo)
        body = bottom_up(replace_var_with_todo, body)
        requires = bottom_up(replace_var_with_todo, requires)
        ensures = bottom_up(replace_var_with_todo, ensures)
    return rule.let(body=body, requires=requires, ensures=ensures), tuple(todos)


def tokens2vars(
        rule: KRule,
        common: tuple[KInner, ...],
        miss_r: tuple[KInner, ...],
        miss_l: tuple[KInner, ...]
) -> tuple[KRule, tuple[KInner, ...], tuple[KInner, ...], tuple[KInner, ...]]:
    count = -1
    body = rule.body
    requires = rule.requires
    ensures = rule.ensures
    result_common = [common[0]]
    result_miss_r = []
    result_miss_l = []

    def _curr_var(s: KSort) -> KVariable:
        nonlocal count
        count += 1
        # todo: may need a #SemanticCastTo + _token.sort
        return KVariable(GEN_VAR_NAME + str(count), s)

    def _replace_tokens_with_vars(_token: KInner, to_replace: KToken, replaced: KVariable) -> KInner:
        if isinstance(_token, KToken) and _token.token == to_replace.token and _token.sort == to_replace.sort:
            return replaced
        return _token

    def _process_tokens(tokens, result_list):
        nonlocal body, requires, ensures
        for token in tokens:
            if not isinstance(token, KToken):
                assert isinstance(token, KVariable)
                result_list.append(token)
                continue
            var = _curr_var(token.sort)
            result_list.append(var)
            replace_tokens_with_vars = partial(_replace_tokens_with_vars, to_replace=token, replaced=var)
            body = bottom_up(replace_tokens_with_vars, body)
            requires = bottom_up(replace_tokens_with_vars, requires)
            ensures = bottom_up(replace_tokens_with_vars, ensures)

    _process_tokens(common[1:], result_common)
    _process_tokens(miss_r, result_miss_r)
    _process_tokens(miss_l, result_miss_l)
    return rule.let(body=body, requires=requires, ensures=ensures), tuple(result_common), tuple(result_miss_r), tuple(result_miss_l)


def lower_priority(rule: KRule) -> KRule:
    # Note that priorities between 50 and 150 are reserved by the LLVM backend
    if Atts.PRIORITY in rule.att:
        new_priority = int(rule.att[Atts.PRIORITY]) + 1
        new_att = rule.att.update([Atts.PRIORITY(new_priority)])
        return rule.let(att=new_att)
    elif Atts.OWISE in rule.att:
        new_att = rule.att.discard([Atts.OWISE])
        new_att = new_att.update([Atts.PRIORITY(201)])
        return rule.let(att=new_att)
    else:
        new_att = rule.att.update([Atts.PRIORITY(151)])
        return rule.let(att=new_att)


def add_check_consistency(
        rule: KRule,
        common: tuple[KInner, ...],
        miss_r: tuple[KInner, ...],
        miss_l: tuple[KInner, ...]
) -> KRule:
    map_var = DEFAULT_COMPLEMENTS_VAR
    k = list_of(common)
    v = list_of([list_of(miss_r), list_of(miss_l)])
    lookup = KApply('_[_]orDefault__MAP_KItem_Map_KItem_KItem', [map_var, k, list_empty()])
    constraint = KApply('_==K_', [lookup, list_empty()])
    constraint = orBool([constraint, KApply('_==K_', [lookup, v])])
    constraint = andBool([rule.requires, constraint])
    return rule.let(requires=constraint)


def content_of_c_holder(
        content_type: str,
        common: tuple[KInner, ...],
        miss_r: tuple[KInner, ...],
        miss_l: tuple[KInner, ...]
) -> KInner:
    match content_type:
        case 'create_r' | 'create_l':
            lhs = DEFAULT_COMPLEMENTS_VAR
            k = list_of(common)
            v = list_of([list_of(miss_r), list_of(miss_l)])
            rhs = KApply('Map:update', [DEFAULT_COMPLEMENTS_VAR, k, v])
            return KRewrite(lhs, rhs)
        case 'put_r':
            k = list_of(common)
            any_miss_r = [KVariable('_' + r.name, r.sort) for r in miss_r if isinstance(r, KVariable)]
            assert len(any_miss_r) == len(miss_r), 'Only variables are allowed in miss_r'
            v_old = list_of([list_of(any_miss_r), list_of(miss_l)])
            v_new = list_of([list_of(miss_r), list_of(miss_l)])
            lhs = map_item(k, v_old)
            rhs = map_item(k, v_new)
            return KRewrite(lhs, rhs)
        case 'put_l':
            k = list_of(common)
            any_miss_l = [KVariable('_' + l.name, l.sort) for l in miss_l if isinstance(l, KVariable)]
            assert len(any_miss_l) == len(miss_l), 'Only variables are allowed in miss_l'
            v_old = list_of([list_of(miss_r), list_of(any_miss_l)])
            v_new = list_of([list_of(miss_r), list_of(miss_l)])
            lhs = map_item(k, v_old)
            rhs = map_item(k, v_new)
            return KRewrite(lhs, rhs)
        case _:
            raise ValueError(f"Unknown content type: {content_type}")


def complements_cell(content: KInner, with_dots: bool) -> KApply:
    if with_dots:
        return KApply('<'+COMPLEMENTS_CELL_NAME+'>', [KApply('#dots'), content, KApply('#dots')])
    else:
        return KApply('<'+COMPLEMENTS_CELL_NAME+'>', [KApply('#noDots'), content, KApply('#noDots')])


def add_c_holder_to_rule(
        rule: KRule,
        content: KInner,
        with_dots: bool = False,
) -> KRule:
    body = rule.body
    assert isinstance(body, KApply), 'Rule body must be a KApply'
    if body.is_cell:
        body = KApply('#cells', [body])
    if body.label.name == '#cells':
        body = body.let(args=(*body.args, complements_cell(content, with_dots)))
        return rule.let(body=body)
    else:
        raise ValueError("Expected a cell or #cells")


def add_c_holder_to_state(
        state: KConfiguration,
) -> KConfiguration:
    # .List
    empty_list = KLabel('.Map')
    empty_list = KApply(empty_list)
    # construct complements-holder cell
    complements_holder = KConfiguration(
        cell_name=COMPLEMENTS_CELL_NAME,
        content=empty_list,
    )
    # add complements-holder to the state
    return KConfiguration(
        cell_name=state.cell_name,
        content=(*state.content, complements_holder),
        multiplicity=state.multiplicity,
        multi_type=state.multi_type,
        att=state.att
    )


def add_c_holder(
        state_or_rule: tuple[KConfiguration | KRule, str],
        content: KInner = None,
        with_dots: bool = False,
) -> tuple[KConfiguration | KRule, str]:
    match state_or_rule:
        case (rule, module_name) if isinstance(rule, KRule):
            return add_c_holder_to_rule(rule, content, with_dots), module_name
        case (state, module_name) if isinstance(state, KConfiguration):
            return add_c_holder_to_state(state), module_name
