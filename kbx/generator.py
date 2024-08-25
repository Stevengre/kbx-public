import contextlib
import shutil
from collections import OrderedDict
from pathlib import Path
from string import Template
from typing import Final, Iterable

from pyk.kast import Atts
from pyk.kast.outer import KDefinition, read_kast_definition, KSentence, KRule, KFlatModule, KImport
from pyk.kast.inner import KApply, KLabel, KInner, KRewrite, KToken, collect, var_occurrences, KVariable, bottom_up, top_down
from pyk.prelude.kint import intToken

from kbx.kompile import kompile, KompileSource
from kbx.outer import get_pure_k_definition, is_from_single_file, KConfiguration
from kbx.pretty_sugar import PrettyPrinterWithSugar
from kbx.utils import has_file_changed
from .prelude import add_c_holder, content_of_c_holder, add_check_consistency, lower_priority, tokens2vars, vars2todos, \
    add_required_modules
from .synchronizer_template import SYNC_TEMPLATE


def inverse_rule(rule: KRule) -> KRule:
    body = rule.body

    def _inverse_rewrite(rewrite: KInner) -> KInner:
        if isinstance(rewrite, KRewrite):
            return KRewrite(rewrite.rhs, rewrite.lhs)
        return rewrite
    body = bottom_up(_inverse_rewrite, body)

    return KRule(
        body=body,
        requires=rule.ensures,
        ensures=rule.requires,
        att=rule.att
    )


def _search_for_complement(
        rule: KRule,
        rule_id: int,
) -> tuple[
    tuple[KInner, ...],
    tuple[KInner, ...],
    tuple[KInner, ...],
]:
    """
    Search for the complement of the rule.
    :param rule: the rule to search for the complement
    :return: a tuple of three tuples (common, miss_r, miss_l)
        - common: [common variables/tokens across different states]
        - miss_r: [variables/tokens unique to the left-hand side]
        - miss_l: [variables/tokens unique to the right-hand side]
    """
    var_token_l = {}  # {cell_name: [variables/tokens on the left-hand side]}
    var_token_r = {}  # {cell_name: [variables/tokens on the right-hand side]}
    # extract asymmetric variables/tokens for each cell
    body = rule.body
    # assert isinstance(body, KApply), "Expected a KApply"

    def _collect_var_token(_term: KInner) -> None:
        if isinstance(_term, KApply) and _term.is_cell:
            if isinstance(_term.args[1], KApply) and _term.args[1].label.name == '#cells':
                return
            tmp_l, tmp_r = _find_cell_asymmetry(_term)
            var_token_l[_term.label.name] = tmp_l
            var_token_r[_term.label.name] = tmp_r

    collect(_collect_var_token, body)

    # if body.is_cell:
    #     tmp_l, tmp_r = _find_cell_asymmetry(body)
    #     var_token_l[body.label.name] = tmp_l
    #     var_token_r[body.label.name] = tmp_r
    # elif body.label.name == '#cells':
    #     for cell in body.args:
    #         assert isinstance(cell, KApply), "Expected a KApply"
    #         tmp_l, tmp_r = _find_cell_asymmetry(cell)
    #         var_token_l[cell.label.name] = tmp_l
    #         var_token_r[cell.label.name] = tmp_r
    # else:
    #     raise ValueError("Expected a cell or #cells")
    # todo: find the common and missing variables/tokens
    all_left = list(OrderedDict.fromkeys(token for tokens in var_token_l.values() for token in tokens))
    all_right = list(OrderedDict.fromkeys(token for tokens in var_token_r.values() for token in tokens))
    cell_common = []
    for cell_name in var_token_l.keys():
        cell_common.extend([token for token in var_token_l[cell_name] if token in var_token_r[cell_name]])
    # [variables/tokens unique to the left-hand side]
    miss_r = [token for token in all_left if token not in all_right]
    # [variables/tokens unique to the right-hand side]
    miss_l = [token for token in all_right if token not in all_left]
    # [rule ID, common variables/tokens across different states]
    common = [intToken(rule_id)] + [token for token in all_left if token in all_right and token not in cell_common]
    return tuple(common), tuple(miss_r), tuple(miss_l)


def _find_cell_asymmetry(
        cell: KApply,
) -> tuple[
    tuple[KInner, ...],
    tuple[KInner, ...],
]:
    """
    Find the asymmetry of the cell.
    :param cell: the cell to find the asymmetry
    :return: a tuple of two tuples (only_l, only_r)
        - var_token_l: [variables/tokens on the left-hand side]
        - var_token_l: [variables/tokens on the right-hand side]
    """
    assert cell.is_cell, "Expected a cell"
    rewrite = cell.args[1]
    if isinstance(rewrite, KRewrite):
        var_token_l = [var[0] for var in var_occurrences(rewrite.lhs).values() if var]
        var_token_l += [tokens[0] for tokens in token_occurrences(rewrite.lhs).values() if tokens]
        var_token_r = [var[0] for var in var_occurrences(rewrite.rhs).values() if var]
        var_token_r += [tokens[0] for tokens in token_occurrences(rewrite.rhs).values() if tokens]
        return tuple(var_token_l), tuple(var_token_r)
    else:
        var_token_l = [var[0] for var in var_occurrences(rewrite).values() if var]
        var_token_l += [tokens[0] for tokens in token_occurrences(rewrite).values() if tokens]
        return tuple(var_token_l), tuple(var_token_l)

def token_occurrences(term: KInner) -> dict[str, list[KToken]]:
    """
    Collect the list of occurrences of each token in a given term.

    :param term: Term to collect token from.
    :return: Dictionary with keys a token names and value as list of all occurrences of that variable.
    """
    _var_occurrences: dict[str, list[KToken]] = {}

    # TODO: should treat #Exists and #Forall specially.
    def _var_occurence(_term: KInner) -> None:
        if isinstance(_term, KToken):
            if _term.token not in _var_occurrences:
                _var_occurrences[_term.token] = []
            _var_occurrences[_term.token].append(_term)

    collect(_var_occurence, term)
    return _var_occurrences


def gen_reverse_priorities(rules: Iterable[KRule]) -> Iterable[int]:
    """
    Give reversed priorities to the rules of the backward transformation.
    """
    o_priorities = []
    for idx, rule in enumerate(rules):
        p = rule.att.get(Atts.PRIORITY)
        if p:
            o_priorities.append((idx, int(p)))
        else:
            o_priorities.append((idx, 50))
    o_priorities.sort(key=lambda x: x[1], reverse=True)
    curr_priority = 30
    prev_priority = o_priorities[0][1]
    priorities = []
    for idx, priority in o_priorities:
        if priority == prev_priority:
            priorities.append((idx, curr_priority))
        else:
            prev_priority = priority
            curr_priority += 2
            if 50 <= curr_priority < 200:
                curr_priority += 150
            priorities.append((idx, curr_priority))
    priorities.sort(key=lambda x: x[0])
    return [priority[1] for priority in priorities]


def change_priority(rule: KRule, priority: int) -> KRule:
    """
    Change the priority of the given rule.
    """
    att = rule.att.discard([Atts.OWISE])
    att = att.update([Atts.PRIORITY(priority)])
    return rule.let(att=att)


def new_priority(rule: KRule, is_create: bool = False) -> KRule:
    if is_create:
        # Delete the priority attribute & Give it a [owise] attribute
        return rule.let(att=rule.att.discard([Atts.PRIORITY]).update([Atts.OWISE(None)]))
    if Atts.OWISE in rule.att:
        return rule.let(att=rule.att.discard([Atts.OWISE]).update([Atts.PRIORITY(200)]))
    return rule


class BXGenerator:
    _printer: PrettyPrinterWithSugar | None = None
    _uni_path: Final[Path]
    _uni_kdef: Final[KDefinition]
    _uni_pure_kdef: Final[KDefinition]
    _uni_modules: Final[dict[str, KFlatModule]]
    _input_cell_name: Final[str]
    _input_cell_endstate: Final[KInner]
    _in_deletes: Final[list[str]]
    _output_cell_name: Final[str]
    _output_sort_name: Final[str]
    _out_deletes: Final[list[str]]
    _default_value: Final[dict[str, str]]

    def __init__(
            self,
            uni_path: Path,
            input_cell_name: str,
            input_cell_endstate: KInner,
            in_deletes: list[str],
            output_cell_name: str,
            output_sort_name: str,
            out_deletes: list[str],
            default_value: dict[str, str] = None
    ) -> None:
        self._uni_path = uni_path
        # Create the folder; if exists, delete it and recreate
        if has_file_changed(self._uni_path):
            if self.kbx_workspace.exists():
                shutil.rmtree(self.kbx_workspace)
            self.kbx_workspace.mkdir(parents=True, exist_ok=True)
            uni_kompiled = kompile(self._uni_path, self.kbx_workspace, KompileSource.UNI)
        else:
            if self.kbx_workspace.exists():
                uni_kompiled = self.kbx_workspace / 'unidirectional-llvm-library'
            else:
                self.kbx_workspace.mkdir(parents=True, exist_ok=True)
                uni_kompiled = kompile(self._uni_path, self.kbx_workspace, KompileSource.UNI)
        # Read the K definition from the generated Kompiled directory
        self._uni_kdef = read_kast_definition(uni_kompiled / 'parsed.json')
        self._printer = PrettyPrinterWithSugar(self._uni_kdef)
        # Filter out the builtins
        self._uni_pure_kdef = get_pure_k_definition(self._uni_kdef)
        # Now, assume that there is only one file
        assert is_from_single_file(self._uni_pure_kdef), "Expected exactly 1 unique user-defined source"
        # sugar all_modules; because we need to manipulate KConfiguration.
        self._uni_modules = {module.name: self._printer.sugar_kflatmodule(module)
                             for module in self._uni_pure_kdef.all_modules}
        self._output_cell_name = output_cell_name
        self._output_sort_name = output_sort_name
        self._input_cell_endstate = input_cell_endstate
        self._input_cell_name = input_cell_name
        self._in_deletes = in_deletes
        self._out_deletes = out_deletes
        if default_value is None:
            default_value = {}
        self._default_value = default_value

    @property
    def kbx_workspace(self) -> Path:
        return self._uni_path.with_name(self._uni_path.stem + '-kbx-workspace')

    def generate(self) -> None:
        # generate the BX definition: Steps 1-5
        forward_k_def, backward_k_def = self.bx_synthesis()

        def _print(k_def: KDefinition, source_type: KompileSource) -> None:
            # print the K definition with sugar & kompile
            k_def_str = self._printer.print_kdefinition(k_def)
            for var_name, var_value in self._default_value.items():
                k_def_str = k_def_str.replace(var_name, var_value)
            tmp_path = self.kbx_workspace / source_type.value / (self._uni_path.stem + '.k')
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, 'w') as tmp_f:
                tmp_f.write(k_def_str)
        # bx.6 print the forward and backward transformations
        forward_k_def = add_required_modules(forward_k_def)
        backward_k_def = add_required_modules(backward_k_def)
        _print(forward_k_def, KompileSource.FOR)
        _print(backward_k_def, KompileSource.BAK)
        script = Template(SYNC_TEMPLATE).substitute({
            'bx_def': self._uni_path.stem + '.k',
            'f_in_cell_name': self._input_cell_name,
            'f_out_cell_name': self._output_cell_name,
            'f_in_delete': self._in_deletes,
            'f_out_delete': self._out_deletes,
        })
        with open(self.kbx_workspace / 'kbx.py', 'w') as f:
            f.write(script)
        print("BX generation completed successfully.")
        print("Please provide default values for `?KbxGenTodo` in the generated K definition of"
              " the backward transformation before synchronization.")

    def bx_synthesis(self) -> tuple[KDefinition, KDefinition]:
        # bx.1. extract the elements of the K definition of Unidirectional Transformation
        syntax, state, rules = self._extract()
        # f.2. construct State+C
        state_c: tuple[KConfiguration, str] = add_c_holder(state)
        # b.2. construct State+C^-1
        state_c_inv: tuple[KConfiguration, str] = self._reverse_io(state_c[0]), state_c[1]
        rules_r: list[tuple[KRule, str]] = []
        rules_l: list[tuple[KRule, str]] = []
        # priorities_l = list(gen_reverse_priorities([rule for rule, _ in rules]))
        for idx, rule in enumerate(rules):
            group = rule[0].att.get(Atts.GROUP)
            if group and group == 'bx':
                rules_r.append(rule)
                rules_l.append(rule)
                continue
            # declare the variables
            put_r: tuple[KRule, str] | None = None
            put_l: tuple[KRule, str] | None = None
            # search for the complement
            common, miss_r, miss_l = _search_for_complement(rule[0], idx)
            if len(miss_r) == 0 and len(miss_l) == 0:
                # f.3. construct CreateR semantic rules
                create_r = rule
                # b.3. construct CreateL semantic rules
                create_l = inverse_rule(rule[0]), rule[1]
                # create_l = change_priority(create_l[0], priorities_l[idx]), create_l[1]
            else:
                # f.3. construct CreateR semantic rules
                create_r_content = content_of_c_holder('create_r', common, miss_r, miss_l)
                create_r = add_c_holder(rule, create_r_content)
                create_r = (add_check_consistency(create_r[0], common, miss_r, miss_l), create_r[1])
                create_r = new_priority(create_r[0], True), create_r[1]
                # create_r = lower_priority(create_r[0]), create_r[1]
                # f.4. construct PutR semantic rules
                var_rule, var_common, var_miss_r, var_miss_l = tokens2vars(rule[0], common, miss_r, miss_l)
                put_r_content = content_of_c_holder('put_r', var_common, var_miss_r, var_miss_l)
                put_r = var_rule, rule[1]
                put_r = add_c_holder(put_r, put_r_content, True)
                put_r = new_priority(put_r[0]), put_r[1]
                # b.4. construct PutL semantic rules
                put_l_content = content_of_c_holder('put_l', var_common, var_miss_r, var_miss_l)
                inv_rule = inverse_rule(var_rule), rule[1]
                put_l = add_c_holder(inv_rule, put_l_content, True)
                put_l = new_priority(put_l[0]), put_l[1]
                # put_l = change_priority(put_l[0], priorities_l[idx]), put_l[1]
                # b.3. construct CreateL semantic rules
                todo_rule, todo_miss_r = vars2todos(inv_rule[0], var_miss_r)
                todo_rule = todo_rule, rule[1]
                create_l_content = content_of_c_holder('create_l', var_common, todo_miss_r, var_miss_l)  # todo
                create_l = add_c_holder(todo_rule, create_l_content)
                create_l = add_check_consistency(create_l[0], var_common, todo_miss_r, var_miss_l), rule[1]
                # create_l = change_priority(create_l[0], priorities_l[idx]), create_l[1]
                # create_l = lower_priority(create_l[0]), create_l[1]
                create_l = new_priority(create_l[0], True), create_l[1]
            assert create_r and create_l, "Expected both create_r and create_l"
            rules_r.extend([create_r, put_r] if put_r else [create_r])
            rules_l.extend([create_l, put_l] if put_l else [create_l])
        # bx.5. construct the KDefinition of the forward transformation and the backward transformation
        forward_k_def = self._construct_kdef(syntax, state_c, rules_r)
        backward_k_def = self._construct_kdef(syntax, state_c_inv, rules_l)
        return forward_k_def, backward_k_def

    def _extract(self) -> tuple[
        list[tuple[KSentence, str]],
        tuple[KConfiguration, str],
        list[tuple[KRule, str]]
    ]:
        """
        Extract the elements of the K definition of Unidirectional Transformation.
        :return: a tuple of the extracted elements (syntax, state, rules) ->split (content, module.name)
        """
        syntax: list[tuple[KSentence, str]] = []
        state: tuple[KConfiguration, str] | None = None
        rules: list[tuple[KRule, str]] = []
        for module in self._uni_modules.values():
            for sentence in module.sentences:
                if isinstance(sentence, KRule):
                    rules.append((sentence, module.name))
                elif isinstance(sentence, KConfiguration):
                    if state is not None:
                        raise ValueError("There are more than one configuration")
                    state = (sentence, module.name)
                else:
                    syntax.append((sentence, module.name))
        return syntax, state, rules

    def _construct_kdef(
            self,
            result_syntax: list[tuple[KSentence, str]],
            result_state: tuple[KConfiguration, str],
            result_rules: list[tuple[KRule, str]]
    ) -> KDefinition:
        result_module_sentences = {}
        for sentence, module_name in result_syntax:
            if module_name not in result_module_sentences:
                result_module_sentences[module_name] = []
            result_module_sentences[module_name].append(sentence)
        for sentence, module_name in result_rules:
            if module_name not in result_module_sentences:
                result_module_sentences[module_name] = []
            result_module_sentences[module_name].append(sentence)
        result_module_sentences[result_state[1]].append(result_state[0])
        # 给result_module_sentences排序
        result_all_modules = []
        for module_name, sentences in result_module_sentences.items():
            sentences.sort(key=lambda x: x.att[Atts.LOCATION] if x.att and Atts.LOCATION in x.att else (0, 0, 0, 0))
            result_all_modules.append(KFlatModule(
                name=module_name,
                sentences=sentences,
                imports=self._uni_modules[module_name].imports,
                att=self._uni_modules[module_name].att
            ))
        result_all_modules.sort(key=lambda x: x.att[Atts.LOCATION])
        return KDefinition(
            main_module_name=self._uni_pure_kdef.main_module_name,
            all_modules=result_all_modules,
            requires=self._uni_pure_kdef.requires,
            att=self._uni_pure_kdef.att
        )

    def _reverse_io(self, config: KConfiguration) -> KConfiguration:
        # change the input with $PGM into its end state
        if config.cell_name == self._output_cell_name:
            assert isinstance(config.content, KInner), "Expected the content to be a KInner"
            content = KVariable('$PGM')
            content = KApply('#SemanticCastTo' + self._output_sort_name, [content])
            return KConfiguration(
                cell_name=config.cell_name,
                content=content,
                multiplicity=config.multiplicity,
                multi_type=config.multi_type,
                att=config.att
            )
        if isinstance(config.content, KApply) and len(config.content.args) == 1:
            pgm = config.content.args[0]
            if isinstance(pgm, KVariable) and pgm.name == '$PGM':
                return KConfiguration(
                    cell_name=config.cell_name,
                    content=self._input_cell_endstate,
                    multiplicity=config.multiplicity,
                    multi_type=config.multi_type,
                    att=config.att
                )
        if isinstance(config.content, tuple):
            content = []
            for cell in config.content:
                content.append(self._reverse_io(cell))
            return KConfiguration(
                cell_name=config.cell_name,
                content=tuple(content),
                multiplicity=config.multiplicity,
                multi_type=config.multi_type,
                att=config.att
            )
        return config
