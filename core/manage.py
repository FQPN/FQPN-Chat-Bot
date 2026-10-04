"""Chat-side command management: !cmlist add/edit/delete/options and
!cmadd / !cmedit / !cmdel. Pure functions on the commands dict so they
can be tested without Twitch.

Command names are exactly what the creator typed (for example "!discord",
"discord" or "hello there"): there is no fixed prefix. Only the built-in
commands below always start with "!"."""

import re

# The built-in commands. The keys are the internal names (also what the settings remember); the values are what people
# type after "!". They are deliberately NOT Nightbot's names (!commands, !addcom, !editcom, !delcom, !title, !game), so
# running both bots in one chat never makes them answer the same message.
BUILTIN_NAMES = {"commands": "cmlist", "addcom": "cmadd", "editcom": "cmedit", "delcom": "cmdel",
                 "title": "settitle", "game": "setgame"}
BUILTIN_KEYS = set(BUILTIN_NAMES)                         # internal names
RESERVED = set(BUILTIN_NAMES.values())                    # typed names, always with "!"
BY_TYPED = {typed: key for key, typed in BUILTIN_NAMES.items()}
BUILTIN_PREFIX = "!"
MAX_NAME = 60
USERLEVELS = {
    "everyone": "everyone",
    "sub": "subscriber", "subscriber": "subscriber",
    "vip": "vip",
    "mod": "moderator", "moderator": "moderator",
    "owner": "broadcaster", "broadcaster": "broadcaster",
}
USERLEVEL_HELP = "everyone, subscriber, vip, moderator, owner"
_FLAG = re.compile(r"^-(ul|cd|a)=(\S*)$", re.IGNORECASE)


class CommandError(Exception):
    pass


def is_reserved(name: str) -> bool:
    """True for names that would collide with a built-in command (!settitle, !setgame, ...)."""
    if name.startswith(BUILTIN_PREFIX):
        first = name[len(BUILTIN_PREFIX):].split(" ", 1)[0]
        return first in RESERVED
    return False


def clean_name(raw: str, prefix: str = "!") -> str:
    """Normalises a name: extra spaces collapsed and lowercase. Nothing else is added or removed."""
    name = " ".join(str(raw).split()).lower()
    if not name:
        raise CommandError("Give the command a name.")
    if len(name) > MAX_NAME:
        raise CommandError(f"Command names can be at most {MAX_NAME} characters.")
    if is_reserved(name):
        raise CommandError(f"'{name}' is a built-in command and can't be used as a name.")
    return name


def names_in_use(commands: dict) -> dict[str, str]:
    """Every command name and alias -> the command it belongs to."""
    used = {}
    for name, c in commands.items():
        used[name] = name
        for a in c.get("aliases", []):
            used[a] = name
    return used


def check_aliases(commands: dict, owner: str, aliases: list[str]) -> None:
    used = names_in_use(commands)
    for a in aliases:
        if is_reserved(a):
            raise CommandError(f"'{a}' is a built-in command and can't be used as a name.")
        if a in used and used[a] != owner:
            raise CommandError(f"'{a}' is already used by another command.")


def match_command(commands: dict, text: str):
    """Finds the command a chat message starts with. Returns (command, rest_of_message) or None.
    The longest matching name wins, so "hello there" beats "hello"."""
    words = text.split()
    low = [w.lower() for w in words]
    best = None
    for key, owner in names_in_use(commands).items():
        kw = key.split()
        n = len(kw)
        if n == 0 or n > len(low) or low[:n] != kw:
            continue
        score = (n, len(key))
        if best is None or score > best[0]:
            best = (score, owner, n)
    if best is None:
        return None
    return best[1], " ".join(words[best[2]:])


def split_name(rest: str) -> tuple[str, str]:
    """Reads the command name from the start of `rest`. Put quotes around a name with spaces:
    !cmadd "hello there" Hi!  ->  ("hello there", "Hi!")"""
    rest = rest.strip()
    if rest[:1] in ('"', "\u201c"):
        close = '"' if rest[0] == '"' else "\u201d"
        end = rest.find(close, 1)
        if end > 0:
            return rest[1:end], rest[end + 1:].strip()
    name, _, tail = rest.partition(" ")
    return name, tail.strip()


def parse_options(text: str, prefix: str = "!") -> tuple[dict, str]:
    """Reads leading -ul= -cd= -a= flags. Everything after them is the response."""
    opts: dict = {}
    rest = text.strip()
    while True:
        first, _, remainder = rest.partition(" ")
        m = _FLAG.match(first)
        if not m:
            break
        key, val = m.group(1).lower(), m.group(2)
        if key == "ul":
            level = USERLEVELS.get(val.lower())
            if not level:
                raise CommandError(f"Unknown user level '{val}'. Use: {USERLEVEL_HELP}.")
            opts["permission"] = level
        elif key == "cd":
            if not val.isdigit() or int(val) > 86400:
                raise CommandError("-cd needs a number of seconds, like -cd=30.")
            opts["cooldown"] = int(val)
        else:
            for a in filter(None, val.split(",")):
                opts.setdefault("aliases", []).append(clean_name(a))
            if not val:
                raise CommandError("-a needs an alias, like -a=!dc.")
        rest = remainder.strip()
    return opts, rest


def _resolve(commands: dict, raw: str, prefix: str = "!") -> tuple[str, str]:
    name = clean_name(raw)
    owner = names_in_use(commands).get(name)
    if owner is None:
        raise CommandError(f"{name} doesn't exist.")
    return name, owner


def add_command(commands: dict, rest: str, prefix: str = "!") -> str:
    raw, tail = split_name(rest)
    if not raw:
        raise CommandError('Usage: !cmadd name [-ul=level] [-cd=seconds] [-a=alias] response  (use "quotes" around a name with spaces)')
    name = clean_name(raw)
    if name in names_in_use(commands):
        raise CommandError(f"{name} already exists. Use !cmedit to change it.")
    opts, response = parse_options(tail)
    if not response:
        raise CommandError("Add the response after the options.")
    aliases = list(dict.fromkeys(opts.get("aliases", [])))
    if name in aliases:
        raise CommandError("A command can't be its own alias.")
    check_aliases(commands, name, aliases)
    commands[name] = {
        "response": response[:450],
        "permission": opts.get("permission", "everyone"),
        "cooldown": opts.get("cooldown", 5),
        "enabled": True,
        "aliases": aliases,
    }
    return name


def edit_command(commands: dict, rest: str, prefix: str = "!", options_only: bool = False) -> str:
    raw, tail = split_name(rest)
    if not raw:
        raise CommandError("Usage: !cmedit name [options] new response")
    _, owner = _resolve(commands, raw)
    opts, response = parse_options(tail)
    if options_only and response:
        raise CommandError("Options only: -ul=, -cd= or -a=. Use edit to change the response.")
    if not opts and not response:
        raise CommandError("Nothing to change. Give a new response or options.")
    if "aliases" in opts:
        new = [a for a in dict.fromkeys(opts["aliases"]) if a != owner]
        check_aliases(commands, owner, new)
        merged = list(dict.fromkeys(commands[owner].get("aliases", []) + new))
        commands[owner]["aliases"] = merged
    if "permission" in opts:
        commands[owner]["permission"] = opts["permission"]
    if "cooldown" in opts:
        commands[owner]["cooldown"] = opts["cooldown"]
    if response:
        commands[owner]["response"] = response[:450]
    return owner


def delete_command(commands: dict, rest: str, prefix: str = "!") -> tuple[str, bool]:
    """Returns (name, was_whole_command). Deleting an alias removes only the alias."""
    raw, _ = split_name(rest)
    if not raw:
        raise CommandError("Usage: !cmdel name")
    name, owner = _resolve(commands, raw)
    if name != owner:
        commands[owner]["aliases"] = [a for a in commands[owner].get("aliases", []) if a != name]
        return name, False
    del commands[owner]
    return name, True
