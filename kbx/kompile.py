from pathlib import Path
from collections.abc import Iterable
from typing import TYPE_CHECKING
from enum import Enum
from pyk.ktool import TypeInferenceMode
from pyk.ktool.kompile import HaskellKompile, KompileArgs, LLVMKompile, LLVMKompileType, MaudeKompile


class KompileSource(Enum):
    UNI = 'unidirectional'
    FOR = 'forward'
    BAK = 'backward'


class KompileTarget(Enum):
    LLVM = 'llvm'
    HASKELL = 'haskell'
    MAUDE = 'maude'

    @property
    def md_selector(self) -> str:
        match self:
            case self.LLVM:
                return 'k & ! symbolic'
            case self.HASKELL | self.MAUDE:
                return 'k & ! concrete'
            case _:
                raise AssertionError()


def kompile(
        main_file: Path,
        output_dir: Path,
        source_type: KompileSource,
        *,
        main_module: str | None = None,
        syntax_module: str | None = None,
        includes: Iterable[Path] = (),
        emit_json: bool = True,
        read_only: bool = False,
        ccopts: Iterable[str] = (),
        optimization: int = 0,
        llvm_kompile_type: LLVMKompileType | None = None,
        enable_llvm_debug: bool = False,
        plugin_dir: Path | None = None,
        debug_build: bool = False,
        debug: bool = False,
        verbose: bool = False,
        type_inference_mode: str | TypeInferenceMode | None = None,
    ) -> Path:
    include_dirs = tuple(includes)
    base_args_llvm = KompileArgs(
                    main_file=main_file,
                    main_module=main_module,
                    syntax_module=syntax_module,
                    include_dirs=include_dirs,
                    md_selector=KompileTarget.LLVM.md_selector,
                    hook_namespaces=(),
                    emit_json=emit_json,
                    read_only=read_only,
                )
    kompile_llvm = LLVMKompile(
        base_args=base_args_llvm,
        ccopts=ccopts,
        opt_level=optimization,
        llvm_kompile_type=LLVMKompileType.C
    )
    return kompile_llvm(
        output_dir=output_dir / (str(source_type.value) + '-llvm-library'),
        debug=debug,
        verbose=verbose,
        type_inference_mode=type_inference_mode,
    )





