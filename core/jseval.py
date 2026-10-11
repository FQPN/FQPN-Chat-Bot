"""$(eval ...): a small, safe interpreter for the JavaScript that Nightbot commands use.

It never runs real code. It understands: numbers, text in quotes, lists [..], var/let/const, statements separated by ";"
(the value of the last one is the result, like Nightbot), + - * / %, comparisons (== === != !== < > <= >=), && || !,
a ? b : c, list[i] / text[i], .length, Math.floor/ceil/round/trunc/abs/sqrt/pow/min/max/random/PI/E, parseInt, parseFloat,
String(), Number(), and text/list tools: toUpperCase toLowerCase trim join split includes indexOf slice charAt replace
concat repeat padStart reverse. Limits: 2000 characters, 20000 steps, text up to 2000 characters, lists up to 1000 items."""
import math
import random
import re

MAX_SRC, MAX_STEPS, MAX_TEXT, MAX_LIST = 2000, 20000, 2000, 1000


class EvalError(Exception):
    pass


_TOK = re.compile(r"""\s*(?:
    (?P<num>\d+\.\d*|\.\d+|\d+)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\$]|\\.)*`)
  | (?P<name>[A-Za-z_$\u0600-\u06ff][A-Za-z0-9_$\u0600-\u06ff]*)
  | (?P<op>===|!==|==|!=|<=|>=|&&|\|\||[-+*/%<>!?:;,.()\[\]=])
)""", re.VERBOSE)
_ESC = {"n": "\n", "t": "\t", "r": "", "\\": "\\", "'": "'", '"': '"', "`": "`", "0": "\0"}


def _tokens(src):
    out, pos = [], 0
    src = src.strip()
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m or m.end() == pos:
            if src[pos:].strip() == "":
                break
            raise EvalError(f"unexpected text near: {src[pos:pos + 12]!r}")
        pos = m.end()
        if m.group("num") is not None:
            out.append(("num", float(m.group("num"))))
        elif m.group("str") is not None:
            raw = m.group("str")[1:-1]
            out.append(("str", re.sub(r"\\(.)", lambda e: _ESC.get(e.group(1), e.group(1)), raw)))
        elif m.group("name") is not None:
            out.append(("name", m.group("name")))
        else:
            out.append(("op", m.group("op")))
    return out


class _Undefined:
    def __repr__(self):
        return "undefined"


UNDEF = _Undefined()


def _num(v):
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip()) if v.strip() else 0.0
        except ValueError:
            return math.nan
    if isinstance(v, list):
        return _num(_text(v)) if len(v) <= 1 else math.nan
    return math.nan


def _text(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        if v == int(v) and abs(v) < 1e21:
            return str(int(v))
        return repr(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return ",".join("" if x is UNDEF or x is None else _text(x) for x in v)
    if v is UNDEF:
        return "undefined"
    if v is None:
        return "null"
    return str(v)


def _truthy(v):
    if isinstance(v, float):
        return v != 0 and not math.isnan(v)
    if isinstance(v, str):
        return v != ""
    return not (v is UNDEF or v is None or v is False)


def _cap(v):
    if isinstance(v, str) and len(v) > MAX_TEXT:
        raise EvalError("text too long")
    if isinstance(v, list) and len(v) > MAX_LIST:
        raise EvalError("list too long")
    if isinstance(v, float) and math.isfinite(v) and abs(v) > 1e300:
        raise EvalError("number out of range")
    return v


def _eq(a, b, strict):
    if strict:
        if type(a) is not type(b) and not (isinstance(a, float) and isinstance(b, float)):
            return False
        return a is b if isinstance(a, list) else a == b
    if isinstance(a, list) or isinstance(b, list):
        return a is b
    if (a is UNDEF or a is None) and (b is UNDEF or b is None):
        return True
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return _num(a) == _num(b)


_MATH = {"floor": math.floor, "ceil": math.ceil, "trunc": math.trunc, "abs": abs, "sqrt": math.sqrt,
         "round": lambda a: math.floor(a + 0.5), "sign": lambda a: (a > 0) - (a < 0)}


class _Interp:
    def __init__(self, toks):
        self.t, self.i, self.steps, self.vars = toks, 0, 0, {}

    def step(self):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise EvalError("too much work")

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else (None, None)

    def at(self, kind, val=None):
        k, v = self.peek()
        return k == kind and (val is None or v == val)

    def take(self, kind=None, val=None):
        k, v = self.peek()
        if k is None or (kind and k != kind) or (val is not None and v != val):
            raise EvalError(f"expected {val or kind}")
        self.i += 1
        return v

    # ---- program: statements separated by ";", result = the last expression's value
    def run(self):
        result = UNDEF
        while self.peek()[0] is not None:
            if self.at("op", ";"):
                self.take()
                continue
            if self.at("name") and self.peek()[1] in ("var", "let", "const"):
                self.take()
                while True:
                    name = self.take("name")
                    self.vars[name] = UNDEF
                    if self.at("op", "="):
                        self.take()
                        self.vars[name] = self.expr()
                    if not self.at("op", ","):
                        break
                    self.take()
                result = UNDEF
            elif self.at("name") and self.peek(1) == ("op", "=") and self.peek(2) != ("op", "="):
                name = self.take()
                self.take()
                result = self.vars[name] = self.expr()
            else:
                result = self.expr()
            if self.peek()[0] is not None and not self.at("op", ";"):
                raise EvalError("expected ;")
        return result

    def expr(self):
        return self.ternary()

    def ternary(self):
        c = self.orr()
        if self.at("op", "?"):
            self.take()
            a = self.expr()
            self.take("op", ":")
            b = self.expr()
            return a if _truthy(c) else b
        return c

    def orr(self):
        x = self.andd()
        while self.at("op", "||"):
            self.take()
            y = self.andd()
            x = x if _truthy(x) else y
        return x

    def andd(self):
        x = self.eq()
        while self.at("op", "&&"):
            self.take()
            y = self.eq()
            x = y if _truthy(x) else x
        return x

    def eq(self):
        x = self.cmp()
        while self.peek()[0] == "op" and self.peek()[1] in ("==", "===", "!=", "!=="):
            op = self.take()
            y = self.cmp()
            r = _eq(x, y, op in ("===", "!=="))
            x = r if op in ("==", "===") else not r
        return x

    def cmp(self):
        x = self.add()
        while self.peek()[0] == "op" and self.peek()[1] in ("<", ">", "<=", ">="):
            op = self.take()
            y = self.add()
            a, b = (x, y) if isinstance(x, str) and isinstance(y, str) else (_num(x), _num(y))
            x = {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
        return x

    def add(self):
        x = self.mul()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.take()
            y = self.mul()
            self.step()
            if op == "+" and (isinstance(x, (str, list)) or isinstance(y, (str, list))):
                x = _cap(_text(x) + _text(y))
            else:
                x = _cap(_num(x) + _num(y) if op == "+" else _num(x) - _num(y))
        return x

    def mul(self):
        x = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/", "%"):
            op = self.take()
            y = self.unary()
            a, b = _num(x), _num(y)
            self.step()
            if op == "*":
                x = _cap(a * b)
            elif b == 0:
                x = math.nan if a == 0 or op == "%" else math.copysign(math.inf, a)
            else:
                x = a / b if op == "/" else math.fmod(a, b)
        return x

    def unary(self):
        if self.at("op", "-"):
            self.take()
            return -_num(self.unary())
        if self.at("op", "+"):
            self.take()
            return _num(self.unary())
        if self.at("op", "!"):
            self.take()
            return not _truthy(self.unary())
        if self.at("name", "typeof"):
            self.take()
            v = self.unary()
            return "string" if isinstance(v, str) else "number" if isinstance(v, float) else "boolean" if isinstance(v, bool) else "object" if isinstance(v, list) or v is None else "undefined"
        return self.postfix()

    def args(self):
        self.take("op", "(")
        out = []
        while not self.at("op", ")"):
            out.append(self.expr())
            if not self.at("op", ")"):
                self.take("op", ",")
        self.take("op", ")")
        return out

    def postfix(self):
        x = self.primary()
        while True:
            self.step()
            if self.at("op", "["):
                self.take()
                k = self.expr()
                self.take("op", "]")
                x = self._index(x, k)
            elif self.at("op", "."):
                self.take()
                name = self.take("name")
                if self.at("op", "("):
                    x = self._method(x, name, self.args())
                elif name == "length" and isinstance(x, (str, list)):
                    x = float(len(x))
                else:
                    raise EvalError(f"unknown property {name}")
            else:
                return x

    def _index(self, x, k):
        if isinstance(x, (list, str)):
            n = _num(k)
            if math.isnan(n) or n != int(n) or not 0 <= n < len(x):
                return UNDEF
            return x[int(n)]
        raise EvalError("only lists and text can be indexed")

    def _method(self, x, name, a):
        s = lambda j, d="": _text(a[j]) if len(a) > j else d
        n = lambda j, d=0: _num(a[j]) if len(a) > j and a[j] is not UNDEF else d
        if isinstance(x, str):
            if name == "toUpperCase": return x.upper()
            if name == "toLowerCase": return x.lower()
            if name == "trim": return x.strip()
            if name == "includes": return s(0) in x
            if name == "startsWith": return x.startswith(s(0))
            if name == "endsWith": return x.endswith(s(0))
            if name == "indexOf": return float(x.find(s(0)))
            if name == "charAt":
                j = int(n(0)); return x[j] if 0 <= j < len(x) else ""
            if name == "slice" or name == "substring":
                st = int(n(0)); en = int(n(1, len(x))) if len(a) > 1 else len(x); return x[st:en]
            if name == "split":
                if not a: return [x]
                sep = s(0); return _cap(list(x) if sep == "" else x.split(sep))
            if name == "replace": return x.replace(s(0), s(1), 1)
            if name == "replaceAll": return _cap(x.replace(s(0), s(1)))
            if name == "repeat": return _cap(x * max(0, int(n(0))))
            if name == "concat": return _cap(x + "".join(_text(v) for v in a))
            if name == "padStart": return _cap(x.rjust(int(n(0)), s(1, " ")[:1] or " "))
            if name == "toString": return x
        if isinstance(x, list):
            if name == "join": return _cap(_text_join(x, s(0, ",")))
            if name == "includes": return any(_eq(v, a[0], True) for v in x) if a else False
            if name == "indexOf":
                for j, v in enumerate(x):
                    if a and _eq(v, a[0], True): return float(j)
                return -1.0
            if name == "slice":
                st = int(n(0)); en = int(n(1, len(x))) if len(a) > 1 else len(x); return x[st:en]
            if name == "reverse": x.reverse(); return x
            if name == "concat": return _cap(x + [v for b in a for v in (b if isinstance(b, list) else [b])])
            if name == "toString": return _text(x)
        if isinstance(x, float):
            if name == "toFixed": return f"{x:.{max(0, min(20, int(n(0))))}f}"
            if name == "toString": return _text(x)
        raise EvalError(f"unknown function {name}")

    def primary(self):
        k, v = self.peek()
        self.step()
        if k == "num":
            self.take(); return v
        if k == "str":
            self.take(); return v
        if k == "op" and v == "(":
            self.take(); x = self.expr(); self.take("op", ")"); return x
        if k == "op" and v == "[":
            self.take(); items = []
            while not self.at("op", "]"):
                items.append(self.expr())
                if not self.at("op", "]"):
                    self.take("op", ",")
            self.take("op", "]")
            return _cap(items)
        if k == "name":
            self.take()
            if v == "true": return True
            if v == "false": return False
            if v == "null": return None
            if v == "undefined": return UNDEF
            if v == "NaN": return math.nan
            if v == "Infinity": return math.inf
            if v == "Math":
                self.take("op", ".")
                f = self.take("name")
                if f == "PI": return math.pi
                if f == "E": return math.e
                a = self.args()
                if f == "random": return random.random()
                if f in ("min", "max"):
                    vals = [_num(x) for x in a]
                    return (min if f == "min" else max)(vals) if vals else (math.inf if f == "min" else -math.inf)
                if f == "pow": return _cap(_num(a[0]) ** _num(a[1])) if len(a) == 2 else math.nan
                if f in _MATH and len(a) >= 1:
                    try:
                        return float(_MATH[f](_num(a[0])))
                    except (ValueError, OverflowError):
                        return math.nan
                raise EvalError(f"unknown function Math.{f}")
            if v in ("parseInt", "parseFloat", "String", "Number", "Boolean", "isNaN"):
                a = self.args(); x = a[0] if a else UNDEF
                if v == "String": return _text(x)
                if v == "Number": return _num(x)
                if v == "Boolean": return _truthy(x)
                if v == "isNaN": return math.isnan(_num(x))
                m = re.match(r"\s*[-+]?(\d+(\.\d*)?|\.\d+)", _text(x))
                if not m: return math.nan
                return float(int(float(m.group(0)))) if v == "parseInt" else float(m.group(0))
            if v in self.vars:
                return self.vars[v]
            raise EvalError(f"unknown name {v}")
        raise EvalError("unexpected symbol")


def _text_join(items, sep):
    return sep.join("" if x is UNDEF or x is None else _text(x) for x in items)


def evaluate(src: str) -> str:
    """The text $(eval ...) puts in the message. Raises EvalError for anything it can't do safely."""
    if len(src) > MAX_SRC:
        raise EvalError("code too long")
    toks = _tokens(src)
    if not toks:
        raise EvalError("empty")
    v = _Interp(toks).run()
    return "" if v is UNDEF else _text(v)
