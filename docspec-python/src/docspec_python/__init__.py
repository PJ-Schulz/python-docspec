# -*- coding: utf8 -*-
# Copyright (c) 2020 Niklas Rosenstein
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

__author__ = "Niklas Rosenstein <rosensteinniklas@gmail.com>"
__version__ = "2.2.1"
__all__ = [
    "Parser",
    "ParserOptions",
    "load_python_modules",
    "parse_python_module",
    "find_module",
    "iter_package_files",
    "DiscoveryResult",
    "discover",
]

import io
import os
import sys
import typing as t
from dataclasses import dataclass
from pathlib import Path

from docspec import Argument, Module
from nr.util.fs import recurse_directory

from .parser import Parser, ParserOptions


def load_python_modules(
    modules: t.Optional[t.Sequence[str]] = None,
    packages: t.Optional[t.Sequence[str]] = None,
    search_path: t.Optional[t.Sequence[t.Union[str, Path]]] = None,
    options: t.Optional[ParserOptions] = None,
    raise_: bool = True,
    encoding: t.Optional[str] = None,
    *,
    files: t.Optional[t.Sequence[t.Tuple[str, str]]] = None,
) -> t.Iterable[Module]:
    """
    Utility function for loading multiple #Module#s from a list of Python module and package
    names. It combines #find_module(), #iter_package_files() and #parse_python_module() in a
    convenient way.

    # Arguments
    modules: A list of module names to load and parse.
    packages: A list of package names to load and parse.
    search_path: The Python module search path. Falls back to #sys.path if omitted.
    options: Options for the Python module parser.
    files: A list of `(module_name, filename)` tuples to parse.

    # Returns
    Iterable of #Module.
    """

    files = list(files or [])
    module_name: t.Optional[str]
    for module_name in modules or []:
        try:
            files.append((module_name, find_module(module_name, search_path)))
        except ImportError:
            if raise_:
                raise
    for package_name in packages or []:
        try:
            _kw = dict(prefered_python_file_type=options.prefered_python_file_type) if options is not None else dict()
            files.extend(iter_package_files(package_name, search_path, **_kw))
        except ImportError:
            if raise_:
                raise

    for module_name, filename in files:
        yield parse_python_module(filename, module_name=module_name, options=options, encoding=encoding)


@t.overload
def parse_python_module(
    filename: t.Union[str, Path],
    module_name: t.Optional[str] = None,
    options: t.Optional[ParserOptions] = None,
    encoding: t.Optional[str] = None,
) -> Module:
    ...


@t.overload
def parse_python_module(
    fp: t.TextIO,
    filename: t.Union[str, Path],
    module_name: t.Optional[str] = None,
    options: t.Optional[ParserOptions] = None,
    encoding: t.Optional[str] = None,
) -> Module:
    ...


def parse_python_module(  # type: ignore
    fp: t.Union[str, Path, t.TextIO],
    filename: t.Union[str, Path, None] = None,
    module_name: t.Optional[str] = None,
    options: t.Optional[ParserOptions] = None,
    encoding: t.Optional[str] = None,
) -> Module:
    """
    Parses Python code of a file or file-like object and returns a #Module
    object with the contents of the file The *options* are forwarded to the
    #Parser constructor.
    """

    if isinstance(fp, (str, Path)):
        if filename:
            raise TypeError('"fp" and "filename" both provided, and "fp" is a string/path')
        # TODO(NiklasRosenstein): If the file header contains a # coding: <name> comment, we should
        #   use that instead of the specified or system default encoding.
        with io.open(fp, encoding=encoding) as fpobj:
            return parse_python_module(fpobj, fp, module_name, options, encoding)

    assert filename is not None
    parser = Parser(options)
    ast = parser.parse_to_ast(fp.read(), str(filename))
    return parser.parse(ast, str(filename), module_name)


def find_module(module_name: str, search_path: t.Optional[t.Sequence[t.Union[str, Path]]] = None) -> str:
    """Finds the filename of a module that can be parsed with #parse_python_module(). If *search_path* is not set,
    the default #sys.path is used to search for the module. If *module_name* is a Python package, it will return the
    path to the package's `__init__.py` file. If the module does not exist, an #ImportError is raised. This is also
    true for PEP 420 namespace packages that do not provide an `__init__.py` file.

    :raise ImportError: If the module cannot be found.
    """

    # NOTE(NiklasRosenstein): We cannot use #pkgutil.find_loader(), #importlib.find_loader()
    #   or #importlib.util.find_spec() as they weill prefer returning the module that is already
    #   loaded in #sys.module even if that instance would not be in the specified search_path.

    if search_path is None:
        search_path = sys.path

    filenames = [
        os.path.join(os.path.join(*module_name.split(".")), "__init__.py"),
        os.path.join(*module_name.split(".")) + ".py",
    ]

    for path in search_path:
        for choice in filenames:
            abs_path = os.path.normpath(os.path.join(path, choice))
            if os.path.isfile(abs_path):
                return abs_path

    raise ImportError(module_name)


def filter_python_file_types(lst: t.List[Path], prefer_python_file_type: str = "py") -> t.List[Path]:
    """
    Remove files from the list based on the preferred Python file type.

    If 'prefer_python_file_type' is 'py', it will remove corresponding '.pyi' files
    when both a '.py' and a '.pyi' file with the same name exist in the list.

    If 'prefer_python_file_type' is 'pyi', it will remove corresponding '.py' files
    under the same conditions.

    Parameters:
    - lst: List[Path]: A list of Path objects representing files.
    - prefer_python_file_type: str: The preferred file type ('py' or 'pyi').

    Returns:
    - List[Path]: A filtered list of Path objects based on the preference.

    Raises:
    - ValueError: If prefer_python_file_type is not 'py' or 'pyi'.
    """
    # Validate the input for prefer_python_file_type
    if prefer_python_file_type not in {"py", "pyi"}:
        raise ValueError("prefer_python_file_type must be either 'py' or 'pyi'")

    # Create a dictionary to track file names without extensions
    base_names = {}
    for file in lst:
        base_name = str(file.with_suffix(""))
        suffix = file.suffix
        if base_name not in base_names:
            base_names[base_name] = set()
        base_names[base_name].add(suffix)

    # Identify conflicting files that have both .py and .pyi
    conflicting_files = {base for base, exts in base_names.items() if ".py" in exts and ".pyi" in exts}

    # Determine which suffix to remove
    opposite_suffix = ".pyi" if prefer_python_file_type == "py" else ".py"

    # Filter the list to exclude opposite files when there's a conflict
    cleaned_list = [
        file for file in lst if not (file.suffix == opposite_suffix and str(file.with_suffix("")) in conflicting_files)
    ]

    return cleaned_list


def iter_package_files(
    package_name: str,
    search_path: t.Optional[t.Sequence[t.Union[str, Path]]] = None,
    prefered_python_file_type: str = "py",
) -> t.Iterable[t.Tuple[str, str]]:
    """Returns an iterator for the Python source files in the specified package. The items returned
    by the iterator are tuples of the module name and filename. Supports a PEP 420 namespace package
    if at least one matching directory with at least one Python source file in it is found.
    """
    encountered: t.Set[str] = set()

    try:
        package_entrypoint = find_module(package_name, search_path)
        encountered.add(package_name)
        yield package_name, package_entrypoint
    except ImportError:
        package_entrypoint = None

    # Find files matching the package name, compatible with PEP 420 namespace packages.
    for path in sys.path if search_path is None else search_path:
        parent_dir = Path(path, *package_name.split("."))
        if not parent_dir.is_dir():
            continue
        lst = list(recurse_directory(parent_dir))
        filtered_lst = filter_python_file_types(lst, prefer_python_file_type=prefered_python_file_type)
        for item in filtered_lst:
            if item.suffix in (".py", ".pyi"):
                parts = item.with_suffix("").relative_to(parent_dir).parts
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                module_name = ".".join((package_name,) + parts)
                if module_name not in encountered:
                    encountered.add(module_name)
                    yield module_name, str(item)


@dataclass
class DiscoveryResult:
    name: str
    Module: t.ClassVar[t.Type["_Module"]]
    Package: t.ClassVar[t.Type["_Package"]]


@dataclass
class _Module(DiscoveryResult):
    filename: str


@dataclass
class _Package(DiscoveryResult):
    directory: str


DiscoveryResult.Module = _Module
DiscoveryResult.Package = _Package


def discover(directory: t.Union[str, Path]) -> t.Iterable[DiscoveryResult]:
    """
    Discovers Python modules and packages in the specified *directory*. The returned generated
    returns tuples where the first element of the tuple is the type (either `'module'` or
    `'package'`), the second is the name and the third is the path. In case of a package,
    the path points to the directory.

    :raises OSError: Propagated from #os.listdir().
    """

    # TODO (@NiklasRosenstein): Introspect the contents of __init__.py files to determine
    #   if we're looking at a namespace package. If we do, continue recursively.

    for name in os.listdir(directory):
        if name.endswith(".py") and name.count(".") == 1:
            yield DiscoveryResult.Module(name[:-3], os.path.join(directory, name))
        else:
            full_path = os.path.join(directory, name, "__init__.py")
            if os.path.isfile(full_path):
                yield DiscoveryResult.Package(name, os.path.join(directory, name))


def format_arglist(args: t.Sequence[Argument], render_type_hints: bool = True) -> str:
    """
    Formats a Python argument list.
    """

    result: t.List[str] = []

    for arg in args:
        parts = []
        if arg.type == Argument.Type.KEYWORD_ONLY and not any(x.startswith("*") for x in result):
            result.append("*")
        parts = [arg.name]
        if arg.datatype and render_type_hints:
            parts.append(": " + arg.datatype)
        if arg.default_value:
            if arg.datatype:
                parts.append(" ")
            parts.append("=")
        if arg.default_value:
            if arg.datatype:
                parts.append(" ")
            parts.append(arg.default_value)
        if arg.type == Argument.Type.POSITIONAL_REMAINDER:
            parts.insert(0, "*")
        elif arg.type == Argument.Type.KEYWORD_REMAINDER:
            parts.insert(0, "**")
        result.append("".join(parts))

    return ", ".join(result)
