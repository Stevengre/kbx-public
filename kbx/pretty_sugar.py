"""
This module contains the PrettyPrinterWithSugar class, which aims to pretty print a K definition with sugar.
The reason for this class is that the PrettyPrinter class in pyk.kast.pretty cannot print a K definition that
1. is able to be kompiled by the K framework
2. is easy to read and understand for humans

Author: Jianhong Zhao
"""
import logging
from typing import Final, Callable, TYPE_CHECKING

from pyk.kast.outer import KDefinition, KAst, KSentence, KAssoc
from pyk.kast.pretty import PrettyPrinter, indent
from pyk.prelude.kbool import TRUE
from pyk.kast.att import Atts, KAtt, EMPTY_ATT, Format, AttKey, _STR
from pyk.kast.inner import KApply, KAs, KInner, KLabel, KRewrite, KSequence, KSort, KToken, KVariable
from pyk.kast.manip import flatten_label, sort_ac_collections, undo_aliases
from pyk.kast.outer import (
    KBubble,
    KClaim,
    KContext,
    KDefinition,
    KFlatModule,
    KImport,
    KNonTerminal,
    KOuter,
    KProduction,
    KRegexTerminal,
    KRequire,
    KRule,
    KRuleLike,
    KSortSynonym,
    KSyntaxAssociativity,
    KSyntaxLexical,
    KSyntaxPriority,
    KSyntaxSort,
    KTerminal,
)

from kbx.outer import KProductionsWithPriority, KProductionList, KConfiguration

_LOGGER: Final = logging.getLogger(__name__)

ATT_MULTI: Final = AttKey('multiplicity', type=_STR)
ATT_TYPE: Final = AttKey('type', type=_STR)


class PrettyPrinterWithSugar(PrettyPrinter):
    def __init__(self, k_def: KDefinition) -> None:
        super().__init__(k_def)

    def print_kdefinition(self, kdefinition: KDefinition) -> str:
        result = ''
        # print the `require` statements
        if len(kdefinition.requires) > 0:
            result += '\n'.join([super()._print_kouter(require) for require in kdefinition.requires])
            result += '\n\n'
        # print the `module` statements
        # kdefinition.main_module_name == kdefinition.all_modules[1].name

        result += '\n\n'.join([self._print_kflatmodule(module) for module in kdefinition.all_modules])
        return result

    def _print_kflatmodule(self, kflatmodule: KFlatModule) -> str:
        kflatmodule = self.sugar_kflatmodule(kflatmodule)
        # print the `module` statement
        result = f"module {kflatmodule.name}\n    "
        # print the `imports` statements
        result += '\n    '.join([self._print_kimport(kimport) for kimport in kflatmodule.imports])
        # print the `sentences` statements
        if len(kflatmodule.sentences) > 0:
            result += '\n\n    '
            result += '\n\n    '.join([self._print_kouter(sentence)
                                       for sentence in kflatmodule.sentences])
        # print the `endmodule` statement
        result += '\n\nendmodule'
        return result

    def sugar_kflatmodule(self, kflatmodule: KFlatModule) -> KFlatModule:
        sentences_with_loc = []
        sentences_without_loc = []
        top_cell = set()
        is_not_top_cell = set()
        cell_att = None
        multi_cells = {}  # cell_name: tuple(sort.name, multiplicity, type)
        for s in kflatmodule.sentences:
            if s.att and Atts.CELL in s.att and isinstance(s, KProduction):
                # find the KProduction for the top cell; and delete the KProductions for cells
                top_cell.add(s.sort)
                for c in s.argument_sorts:
                    if c.name.endswith("CellList"):
                        is_not_top_cell.add(KSort(c.name[:-4]))
                    if c.name.endswith("CellMap"):
                        is_not_top_cell.add(KSort(c.name[:-3]))
                    is_not_top_cell.add(c)
                if s.att.get(ATT_MULTI):
                    assert s.att.get(ATT_TYPE), f"Expected the type attribute to be set for the cell {s.sort}"
                    multi_cells[s.items[0].value[1:-1]] = (s, s.att[ATT_MULTI], s.att[ATT_TYPE])
                top_cell.difference_update(is_not_top_cell)
                if Atts.LOCATION in s.att and (not cell_att or cell_att[Atts.LOCATION] > s.att[Atts.LOCATION]):
                    cell_att = s.att
                continue
                # todo: now is ok: this ask user not to use the auto-gen top cell, but define it manually
            if s.att and Atts.LOCATION in s.att:
                sentences_with_loc.append(s)
            else:
                sentences_without_loc.append(s)
        if len(top_cell) > 0:
            assert len(top_cell) == 1, f"Expected exactly 1 top cell, but found {len(top_cell)}"
            assert cell_att, "Expected the top cell to have a location attribute"
            kconfig = self.definition.init_config(top_cell.pop())
            kconfig = KConfiguration.from_kinner(kconfig, multi_cells, self.definition)
            kconfig = kconfig.let_att(cell_att)
            sentences_with_loc.append(kconfig)
        # sort the sentences by location
        sentences_with_loc.sort(key=lambda x: x.att[Atts.LOCATION])
        # todo: process the sentences without location
        for s in sentences_without_loc:
            if isinstance(s, KSyntaxPriority):
                # produce the KProductionsWithPriority
                k_productions = []
                att = None
                for group in s.priorities:
                    k_production_group = []
                    for label in group:
                        # find the KProduction from sentences_with_loc
                        new_sentence_with_loc = []
                        for sentence in sentences_with_loc:
                            if isinstance(sentence, KProduction) and sentence.klabel:
                                if sentence.klabel.name == label:
                                    k_production_group.append(sentence)
                                    if not att:
                                        att = sentence.att
                                    continue
                            new_sentence_with_loc.append(sentence)
                        sentences_with_loc = new_sentence_with_loc
                    k_productions.append(k_production_group)
                k_productions_with_priority = KProductionsWithPriority(k_productions, att)
                sentences_with_loc.append(k_productions_with_priority)
                continue
                # todo: now is ok: I may need to consider the case
                #  where the KProduction(s) are duplicate in priorities;
                #  Also, there may have more cases to consider.
            if isinstance(s, KSyntaxAssociativity):
                continue
                # because this attribute is already in the KProduction
                # todo: now is ok: I may need to check
                #  if the associativity is correct;
                #  if not, I need to add it to the KProduction.
            pass
            # todo: raise NotImplementedError(f"Found a sentence without location: {s}")
        # todo: process the sentences with location
        sentences_with_loc_new = []
        for s in sentences_with_loc:
            if isinstance(s, KProduction):
                # generate KProductionList `syntax _ ::= List{_, "_"}` for the user list
                if s.att.get(Atts.USER_LIST):
                    symbol = s.att.get(Atts.SYMBOL)
                    if symbol and symbol.startswith('.List'):
                        continue
                    new = KProductionList.from_kproduction(s)
                    sentences_with_loc_new.append(new)
                    continue
            sentences_with_loc_new.append(s)
        sentences_with_loc = sentences_with_loc_new
        sentences_with_loc.sort(key=lambda x: x.att[Atts.LOCATION] if x.att is not None else (0, 0, 0, 0))
        return KFlatModule(
            name=kflatmodule.name,
            sentences=sentences_with_loc,
            imports=kflatmodule.imports,
            att=kflatmodule.att
        )

    def _print_kimport(self, kimport: KImport) -> str:
        return ' '.join(['imports', ('' if kimport.public else 'private'), kimport.name])

    def _print_kouter(self, sentence: KOuter) -> str:
        if isinstance(sentence, KProductionsWithPriority):
            return self._print_kproductions_with_priority(sentence)
        if isinstance(sentence, KProductionList):
            return sentence.pretty_print() + ' ' + self._print_katt(sentence.att)
        if isinstance(sentence, KConfiguration):
            return self._print_kconfiguration(sentence)
        if isinstance(sentence, KRule):
            body = '\n     '.join(self.print(sentence.body).split('\n'))
            rule_str = 'rule '
            rule_str = rule_str + ' ' + body
            atts_str = self.print(sentence.att)
            if sentence.requires != TRUE:
                requires_str = 'requires ' + '\n  '.join(self._print_kast_bool(sentence.requires).split('\n'))
                rule_str = rule_str + '\n  ' + requires_str
            if sentence.ensures != TRUE:
                ensures_str = 'ensures ' + '\n  '.join(self._print_kast_bool(sentence.ensures).split('\n'))
                rule_str = rule_str + '\n   ' + ensures_str
            return rule_str + '\n  ' + atts_str
        return super()._print_kouter(sentence)

    def _print_kproductions_with_priority(self, psp: KProductionsWithPriority) -> str:
        assert len(psp.priorities) > 0
        assert len(psp.priorities[0]) > 0
        result = 'syntax ' + super().print(psp.priorities[0][0].sort) + ' ::= '
        _indent = (len(result) + 2) * ' '
        syntax_strs = []
        for ps in psp.priorities:
            syntax_str = f"\n{_indent}| ".join([
                ' '.join([super()._print_kouter(pi) for pi in p.items]) + ' ' + self._print_katt(p.att)
                for p in ps
            ])
            syntax_strs.append(syntax_str)
        result += f"\n{_indent}> ".join(syntax_strs)
        return result

    def _print_katt(self, att: KAtt) -> str:
        att = att.drop_source()
        att = att.discard([Atts.BRACKET_LABEL, Atts.KLABEL, Atts.PRODUCTION, Atts.LABEL])
        # todo: now is ok; more claver way to print the klabel
        if not att:
            return ''
        att_strs: list[str] = []
        for key, value in att.items():
            if key == Atts.FORMAT:
                assert isinstance(value, Format), f"Expected the value of the format attribute to be a Format, but found {type(value)}"
                value_str = ''.join(value.tokens)
                att_strs.append(f'format({value_str})')
                continue
            value_str = key.type.unparse(value)
            if value_str is None:
                att_strs.append(key.name)
            else:
                if value_str == '':
                    att_strs.append(key.name)
                else:
                    att_strs.append(f'{key.name}({value_str})')
        return f'[{", ".join(att_strs)}]'

    def _print_kconfiguration(self, sentence: KConfiguration) -> str:
        return "configuration \n" + self._print_konfiguration_cell(sentence, 6)

    def _print_konfiguration_cell(self, cell: KConfiguration, _indent: int) -> str:
        indent_str = " " * _indent
        result = indent_str + f"<{cell.cell_name}"
        if cell.multiplicity and cell.multi_type:
            result += f" multiplicity=\"{cell.multiplicity}\" type=\"{cell.multi_type}\""
        result += ">"
        if isinstance(cell.content, KInner):
            result += " " + self._print_kinner(cell.content) + " "
        else:
            for c in cell.content:
                result += "\n"
                result += self._print_konfiguration_cell(c, _indent + 2)
            result += f"\n{indent_str}"
        result += f"</{cell.cell_name}>"
        return result

    def _print_kinner(self, inner: KInner) -> str:
        if isinstance(inner, KApply):
            if inner.label.name.startswith('#SemanticCastTo'):
                return '(' + super()._print_kinner(inner.args[0]) + '):' + inner.label.name[15:]
            if inner.label.name == '#cells':
                if len(inner.args) == 0:
                    return '.Bag'
                return '\n' + '\n'.join([self._print_kinner(a) for a in inner.args])
        if isinstance(inner, KToken):
            if inner.sort.name not in ['Int', 'String', 'Bool']:
                return f'#token("{inner.token}", "{inner.sort.name}")'
        return super()._print_kinner(inner)

