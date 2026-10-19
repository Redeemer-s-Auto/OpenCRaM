# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A small, safe formula language for custom fields (Notion-style).

Examples:
    prop("Amount") * 1.0825
    if(prop("Approved"), "Yes", "No")
    dateAdd(prop("Call-back"), 7, "days")
    concat(prop("Year"), " ", prop("Make"), " ", prop("Model"))
    round(prop("Hours") * 165, 2)

Nothing here calls ``eval``. Text is tokenized and parsed into a tree, and the
tree is walked with a fixed set of functions. Bad formulas raise FormulaError
when an admin saves them; problems at run time (a missing value, divide by
zero) give an empty result instead of an error.
"""

# Python imports
import datetime
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MAX_FORMULA_LENGTH = 2000
MAX_DEPTH = 50


class FormulaError(Exception):
    """A formula that cannot be parsed or uses an unknown name."""


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<op>==|!=|>=|<=|&&|\|\||[-+*/%(),<>!])
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)


def _tokenize(text):
    tokens = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise FormulaError(f"Unexpected character '{text[pos]}' at position {pos + 1}.")
        kind = match.lastgroup
        value = match.group(kind)
        pos = match.end()
        if kind == "ws":
            continue
        if kind == "string":
            body = value[1:-1]
            value = re.sub(r"\\(.)", r"\1", body)
        tokens.append((kind, value))
    tokens.append(("end", None))
    return tokens


# ---------------------------------------------------------------------------
# Parser (precedence climbing) -> tuples
#   ("num", Decimal) ("str", s) ("bool", b) ("call", name, [args])
#   ("bin", op, left, right) ("not", x) ("neg", x)
# ---------------------------------------------------------------------------

_KEYWORDS = {"true", "false", "and", "or", "not"}


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.depth = 0

    def peek(self):
        return self.tokens[self.i]

    def take(self, kind=None, value=None):
        tok = self.tokens[self.i]
        if kind and tok[0] != kind or value is not None and tok[1] != value:
            want = value or kind
            got = tok[1] if tok[1] is not None else "the end"
            raise FormulaError(f"Expected {want} but found {got}.")
        self.i += 1
        return tok

    def is_op(self, *ops):
        tok = self.peek()
        return (tok[0] == "op" and tok[1] in ops) or (tok[0] == "name" and tok[1] in ops)

    def parse(self):
        node = self.expr()
        if self.peek()[0] != "end":
            raise FormulaError(f"Unexpected '{self.peek()[1]}'.")
        return node

    def expr(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError("The formula is nested too deeply.")
        try:
            return self.or_()
        finally:
            self.depth -= 1

    def or_(self):
        node = self.and_()
        while self.is_op("||", "or"):
            self.i += 1
            node = ("bin", "or", node, self.and_())
        return node

    def and_(self):
        node = self.not_()
        while self.is_op("&&", "and"):
            self.i += 1
            node = ("bin", "and", node, self.not_())
        return node

    def not_(self):
        if self.is_op("!", "not"):
            self.i += 1
            return ("not", self.not_())
        return self.cmp()

    def cmp(self):
        node = self.add()
        if self.is_op("==", "!=", ">", ">=", "<", "<="):
            op = self.take()[1]
            node = ("bin", op, node, self.add())
        return node

    def add(self):
        node = self.mul()
        while self.is_op("+", "-"):
            op = self.take()[1]
            node = ("bin", op, node, self.mul())
        return node

    def mul(self):
        node = self.unary()
        while self.is_op("*", "/", "%"):
            op = self.take()[1]
            node = ("bin", op, node, self.unary())
        return node

    def unary(self):
        if self.is_op("-"):
            self.i += 1
            return ("neg", self.unary())
        return self.primary()

    def primary(self):
        kind, value = self.peek()
        if kind == "number":
            self.i += 1
            return ("num", Decimal(value))
        if kind == "string":
            self.i += 1
            return ("str", value)
        if kind == "op" and value == "(":
            self.i += 1
            node = self.expr()
            self.take("op", ")")
            return node
        if kind == "name":
            self.i += 1
            if value in ("true", "false"):
                return ("bool", value == "true")
            is_call = self.peek()[0] == "op" and self.peek()[1] == "("
            if value in _KEYWORDS and not (value in ("and", "or") and is_call):
                raise FormulaError(f"'{value}' cannot start a value.")
            if not (self.peek()[0] == "op" and self.peek()[1] == "("):
                raise FormulaError(f"'{value}' must be followed by ( ). Use prop(\"Field name\") for fields.")
            self.i += 1
            args = []
            if not (self.peek()[0] == "op" and self.peek()[1] == ")"):
                args.append(self.expr())
                while self.peek()[0] == "op" and self.peek()[1] == ",":
                    self.i += 1
                    args.append(self.expr())
            self.take("op", ")")
            if value not in FUNCTIONS:
                raise FormulaError(f"Unknown function '{value}'.")
            low, high = FUNCTIONS[value][1]
            if len(args) < low or (high is not None and len(args) > high):
                raise FormulaError(f"{value}() takes {_arity_text(low, high)}.")
            if value == "prop" and args[0][0] != "str":
                raise FormulaError('prop() needs a field name in quotes, like prop("Amount").')
            return ("call", value, args)
        if value is None:
            raise FormulaError("The formula ends too early.")
        raise FormulaError(f"Unexpected '{value}'.")


def _arity_text(low, high):
    if high is None:
        return f"at least {low} value{'s' if low != 1 else ''}"
    if low == high:
        return f"{low} value{'s' if low != 1 else ''}"
    return f"{low} to {high} values"


def parse(text):
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("The formula is empty.")
    if len(text) > MAX_FORMULA_LENGTH:
        raise FormulaError(f"A formula can be at most {MAX_FORMULA_LENGTH} characters.")
    return _Parser(_tokenize(text)).parse()


def referenced_names(tree):
    """Field names used through prop("...")."""
    names = []

    def walk(node):
        if node[0] == "call":
            if node[1] == "prop":
                names.append(node[2][0][1])
            for arg in node[2]:
                walk(arg)
        elif node[0] == "bin":
            walk(node[2])
            walk(node[3])
        elif node[0] in ("not", "neg"):
            walk(node[1])

    walk(tree)
    return names


def rename_prop(text, old, new):
    """Rewrite prop("old") to prop("new") in a formula's text."""

    def quote(name):
        return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'

    pattern = re.compile(r"prop\(\s*([\"'])" + re.escape(old) + r"\1\s*\)")
    return pattern.sub(lambda _m: f"prop({quote(new)})", text)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _to_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.replace(",", "").replace("$", "").strip())
        except InvalidOperation:
            return None
    return None


def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        text = format(value.normalize(), "f")
        return text
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(_to_text(v) for v in value)
    return str(value)


def _truthy(value):
    if value is None:
        return False
    if isinstance(value, (list, str)):
        return len(value) > 0
    if isinstance(value, Decimal):
        return value != 0
    return bool(value)


def _as_date(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value
    return None


_UNITS = {"days", "day", "weeks", "week", "months", "month", "years", "year", "hours", "hour", "minutes", "minute"}


def _add_to_date(date, amount, unit):
    if date is None or amount is None or unit not in _UNITS:
        return None
    n = int(amount)
    unit = unit.rstrip("s")
    if unit in ("day", "week"):
        return date + datetime.timedelta(days=n * (7 if unit == "week" else 1))
    if unit in ("hour", "minute"):
        if not isinstance(date, datetime.datetime):
            date = datetime.datetime.combine(date, datetime.time(), tzinfo=datetime.timezone.utc)
        return date + datetime.timedelta(hours=n if unit == "hour" else 0, minutes=n if unit == "minute" else 0)
    months = n * (12 if unit == "year" else 1)
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    # clamp the day to the last day of the target month
    for day in (date.day, 30, 29, 28):
        try:
            return date.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return None


def _date_between(a, b, unit):
    a, b = _as_date(a), _as_date(b)
    if a is None or b is None or unit not in _UNITS:
        return None
    if isinstance(a, datetime.datetime) != isinstance(b, datetime.datetime):
        a = a.date() if isinstance(a, datetime.datetime) else a
        b = b.date() if isinstance(b, datetime.datetime) else b
    unit = unit.rstrip("s")
    if unit in ("year", "month"):
        months = (a.year - b.year) * 12 + (a.month - b.month)
        if a.day < b.day:
            months -= 1 if months > 0 else 0
        return Decimal(months // 12 if unit == "year" else months)
    delta = a - b
    seconds = delta.total_seconds() if isinstance(delta, datetime.timedelta) else 0
    per = {"day": 86400, "week": 604800, "hour": 3600, "minute": 60}[unit]
    return Decimal(int(seconds // per))


def _round(value, places=None):
    number = _to_number(value)
    if number is None:
        return None
    digits = int(_to_number(places) or 0)
    quant = Decimal(1).scaleb(-digits)
    return number.quantize(quant, rounding=ROUND_HALF_UP)


def _numbers(args):
    flat = []
    for arg in args:
        flat.extend(arg if isinstance(arg, list) else [arg])
    return [n for n in (_to_number(v) for v in flat) if n is not None]


# name -> (implementation, (min args, max args or None)); prop/if/and/or are special-cased.
FUNCTIONS = {
    "prop": (None, (1, 1)),
    "if": (None, (3, 3)),
    "and": (None, (2, None)),
    "or": (None, (2, None)),
    "not": (lambda v: not _truthy(v), (1, 1)),
    "empty": (lambda v: v is None or v == "" or v == [], (1, 1)),
    "round": (_round, (1, 2)),
    "floor": (lambda v: None if _to_number(v) is None else Decimal(int(_to_number(v).__floor__())), (1, 1)),
    "ceil": (lambda v: None if _to_number(v) is None else Decimal(int(_to_number(v).__ceil__())), (1, 1)),
    "abs": (lambda v: None if _to_number(v) is None else abs(_to_number(v)), (1, 1)),
    "min": (lambda *a: min(_numbers(a)) if _numbers(a) else None, (1, None)),
    "max": (lambda *a: max(_numbers(a)) if _numbers(a) else None, (1, None)),
    "sum": (lambda *a: sum(_numbers(a), Decimal(0)), (1, None)),
    "toNumber": (_to_number, (1, 1)),
    "format": (_to_text, (1, 1)),
    "concat": (lambda *a: "".join(_to_text(v) for v in a), (1, None)),
    "length": (lambda v: Decimal(len(v)) if isinstance(v, (str, list)) else Decimal(len(_to_text(v))), (1, 1)),
    "lower": (lambda v: _to_text(v).lower(), (1, 1)),
    "upper": (lambda v: _to_text(v).upper(), (1, 1)),
    "contains": (
        lambda v, s: (_to_text(s) in v) if isinstance(v, list) else (_to_text(s).lower() in _to_text(v).lower()),
        (2, 2),
    ),
    "dateAdd": (lambda d, n, u: _add_to_date(_as_date(d), _to_number(n), _to_text(u)), (3, 3)),
    "dateSubtract": (
        lambda d, n, u: _add_to_date(_as_date(d), None if _to_number(n) is None else -_to_number(n), _to_text(u)),
        (3, 3),
    ),
    "dateBetween": (lambda a, b, u: _date_between(a, b, _to_text(u)), (3, 3)),
    "year": (lambda d: Decimal(_as_date(d).year) if _as_date(d) else None, (1, 1)),
    "month": (lambda d: Decimal(_as_date(d).month) if _as_date(d) else None, (1, 1)),
    "day": (lambda d: Decimal(_as_date(d).day) if _as_date(d) else None, (1, 1)),
}


class _Missing(Exception):
    """A value needed for the result is not there. The result becomes empty."""


def evaluate(tree, get_prop):
    """Walk ``tree``. ``get_prop(name)`` returns a field's value (or None)."""

    def ev(node):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "bool":
            return node[1]
        if kind == "neg":
            n = _to_number(ev(node[1]))
            if n is None:
                raise _Missing()
            return -n
        if kind == "not":
            return not _truthy(ev(node[1]))
        if kind == "bin":
            op = node[1]
            if op == "and":
                return _truthy(ev(node[2])) and _truthy(ev(node[3]))
            if op == "or":
                return _truthy(ev(node[2])) or _truthy(ev(node[3]))
            left, right = ev(node[2]), ev(node[3])
            return _binary(op, left, right)
        if kind == "call":
            name, args = node[1], node[2]
            if name == "prop":
                return get_prop(args[0][1])
            if name == "if":
                return ev(args[1]) if _truthy(ev(args[0])) else ev(args[2])
            if name == "and":
                return all(_truthy(ev(a)) for a in args)
            if name == "or":
                return any(_truthy(ev(a)) for a in args)
            return FUNCTIONS[name][0](*[ev(a) for a in args])
        raise FormulaError("Bad formula.")

    try:
        return ev(tree)
    except (_Missing, InvalidOperation, ZeroDivisionError, OverflowError, ValueError, TypeError):
        return None


def _binary(op, left, right):
    if op == "+":
        if isinstance(left, str) or isinstance(right, str):
            return _to_text(left) + _to_text(right)
        if _as_date(left) is not None:
            raise _Missing()
    if op in ("+", "-", "*", "/", "%"):
        a, b = _to_number(left), _to_number(right)
        if a is None or b is None:
            raise _Missing()
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        return a % b
    if op in ("==", "!="):
        if isinstance(left, Decimal) or isinstance(right, Decimal):
            equal = _to_number(left) == _to_number(right)
        else:
            equal = left == right
        return equal if op == "==" else not equal
    # ordering
    if _as_date(left) is not None and _as_date(right) is not None:
        a, b = left, right
    elif isinstance(left, str) and isinstance(right, str):
        a, b = left, right
    else:
        a, b = _to_number(left), _to_number(right)
        if a is None or b is None:
            raise _Missing()
    try:
        return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]
    except TypeError:
        raise _Missing()
