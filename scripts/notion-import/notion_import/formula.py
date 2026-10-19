"""Translate a Notion formula into a Notes formula, or say why it cannot be.

Notion (formulas 2.0) and Notes share prop("Name"), + - * / %, comparisons,
and/or/not and many function names. Notion also allows method calls
(`x.dateAdd(5, "days")`), `ifs(...)`, lists, `let` and more. This module
parses the Notion text into a small tree, rewrites what has a Notes
equivalent, and refuses anything else so the importer can fall back to a
frozen text snapshot instead of creating a wrong formula.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

# Notion function -> Notes function (same argument order).
FUNCTIONS = {
    "if": "if", "and": "and", "or": "or", "not": "not", "empty": "empty",
    "round": "round", "floor": "floor", "ceil": "ceil", "abs": "abs",
    "min": "min", "max": "max", "sum": "sum", "toNumber": "toNumber",
    "format": "format", "concat": "concat", "length": "length",
    "lower": "lower", "upper": "upper", "contains": "contains",
    "dateAdd": "dateAdd", "dateSubtract": "dateSubtract", "dateBetween": "dateBetween",
    "year": "year", "month": "month", "date": "day",  # Notion date() = day of the month
}
UNITS = {"days", "weeks", "months", "years", "hours", "minutes",
         "day", "week", "month", "year", "hour", "minute"}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<op>==|!=|>=|<=|&&|\|\||[-+*/%(),<>!.?:\[\]])
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
""", re.VERBOSE)


class Untranslatable(Exception):
    pass


def _tokens(text: str):
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise Untranslatable(f"unexpected character {text[pos]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        val = m.group(kind)
        if kind == "string":
            val = json.loads(val)
        out.append((kind, val))
    out.append(("end", None))
    return out


class _P:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        return self.t[self.i + k]

    def is_(self, *vals):
        k, v = self.peek()
        return k in ("op", "name") and v in vals

    def take(self, val=None):
        tok = self.t[self.i]
        if val is not None and tok[1] != val:
            raise Untranslatable(f"expected {val!r}")
        self.i += 1
        return tok

    def parse(self):
        n = self.expr()
        if self.peek()[0] != "end":
            raise Untranslatable(f"unexpected {self.peek()[1]!r}")
        return n

    def expr(self):
        n = self.or_()
        if self.is_("?"):
            self.take()
            a = self.expr()
            self.take(":")
            b = self.expr()
            n = ("call", "if", [n, a, b])
        return n

    def or_(self):
        n = self.and_()
        while self.is_("||", "or"):
            self.take()
            n = ("bin", "or", n, self.and_())
        return n

    def and_(self):
        n = self.not_()
        while self.is_("&&", "and"):
            self.take()
            n = ("bin", "and", n, self.not_())
        return n

    def not_(self):
        if self.is_("!", "not"):
            self.take()
            return ("not", self.not_())
        return self.cmp()

    def cmp(self):
        n = self.add()
        if self.is_("==", "!=", ">", ">=", "<", "<="):
            op = self.take()[1]
            n = ("bin", op, n, self.add())
        return n

    def add(self):
        n = self.mul()
        while self.is_("+", "-"):
            op = self.take()[1]
            n = ("bin", op, n, self.mul())
        return n

    def mul(self):
        n = self.unary()
        while self.is_("*", "/", "%"):
            op = self.take()[1]
            n = ("bin", op, n, self.unary())
        return n

    def unary(self):
        if self.is_("-"):
            self.take()
            return ("neg", self.unary())
        return self.postfix()

    def postfix(self):
        n = self.primary()
        while self.is_("."):
            self.take()
            kind, name = self.take()
            if kind != "name":
                raise Untranslatable("bad method call")
            args = self.args() if self.is_("(") else []
            n = ("call", name, [n] + args)
        if self.is_("["):
            raise Untranslatable("lists are not supported")
        return n

    def args(self):
        self.take("(")
        args = []
        if not self.is_(")"):
            args.append(self.expr())
            while self.is_(","):
                self.take()
                args.append(self.expr())
        self.take(")")
        return args

    def primary(self):
        kind, val = self.peek()
        if kind == "number":
            self.take()
            return ("num", val)
        if kind == "string":
            self.take()
            return ("str", val)
        if kind == "op" and val == "(":
            self.take()
            n = self.expr()
            self.take(")")
            return n
        if kind == "op" and val == "[":
            raise Untranslatable("lists are not supported")
        if kind == "name":
            self.take()
            if val in ("true", "false"):
                return ("bool", val)
            if not self.is_("("):
                raise Untranslatable(f"{val!r} is not supported")
            return ("call", val, self.args())
        raise Untranslatable(f"unexpected {val!r}")


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


PropMap = Callable[[str], Optional[str]]


def translate(expression: str, prop_name: PropMap) -> str:
    """Return the Notes expression. `prop_name(notion_name)` gives the Notes
    name to reference (or None when that property cannot be used in a formula).
    Raises Untranslatable."""
    if not expression or not expression.strip():
        raise Untranslatable("empty formula")
    if "{{notion:" in expression:
        raise Untranslatable("formula uses internal property ids")
    tree = _P(_tokens(expression)).parse()
    return _emit(tree, prop_name)


def _emit(n, pm: PropMap) -> str:
    kind = n[0]
    if kind == "num":
        return n[1]
    if kind == "str":
        return _q(n[1])
    if kind == "bool":
        return n[1]
    if kind == "neg":
        return f"-{_emit(n[1], pm)}"
    if kind == "not":
        return f"not({_emit(n[1], pm)})"
    if kind == "bin":
        op = {"and": "and", "or": "or"}.get(n[1], n[1])
        return f"({_emit(n[2], pm)} {op} {_emit(n[3], pm)})"
    if kind == "call":
        name, args = n[1], n[2]
        if name == "prop":
            if len(args) != 1 or args[0][0] != "str":
                raise Untranslatable("prop() needs a name")
            target = pm(args[0][1])
            if not target:
                raise Untranslatable(f"uses property {args[0][1]!r}, which cannot be used in a Notes formula")
            return f"prop({_q(target)})"
        if name == "ifs":
            if len(args) < 3 or len(args) % 2 == 0:
                raise Untranslatable("ifs() needs pairs and a fallback")
            out = _emit(args[-1], pm)
            for i in range(len(args) - 3, -1, -2):
                out = f"if({_emit(args[i], pm)}, {_emit(args[i + 1], pm)}, {out})"
            return out
        if name == "empty" and not args:
            return 'toNumber("")'  # an empty value
        if name in ("dateAdd", "dateSubtract", "dateBetween"):
            if len(args) != 3 or args[2][0] != "str" or args[2][1] not in UNITS:
                raise Untranslatable(f"{name}() unit is not supported")
        if name not in FUNCTIONS:
            raise Untranslatable(f"function {name}() has no Notes equivalent")
        return f"{FUNCTIONS[name]}({', '.join(_emit(a, pm) for a in args)})"
    raise Untranslatable("unsupported expression")


def referenced_props(expression: str) -> list:
    """Notion property names a formula reads (best effort)."""
    return [json.loads(m) for m in re.findall(r'prop\(\s*("(?:[^"\\]|\\.)*")\s*\)', expression or "")]
