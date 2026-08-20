"""Render lichess_bot/config.yml for one era and write it where lichess-bot looks.

Two jobs, both about not repeating ourselves:

  1. Fill the %ERA_NAME% / %ERA_YEARS% placeholders in the greetings from
     config/eras.yaml, so each era account speaks in its own period without
     five near-identical config files (and without hardcoding the era list).
  2. Fail fast on the things that silently break a live bot: a missing token,
     an unknown era, or a greeting over Lichess's 140-character chat limit
     (those messages are simply never delivered — an invisible failure).

    python -m lichess_bot.render_config /app/lichess-bot/config.yml
"""
import os
import sys
from pathlib import Path

from backend.engine_pool import CFG

from lichess_bot.engine import era_from_env

SRC = Path(__file__).resolve().parent / "config.yml"
MAX_CHAT_LEN = 140          # lichess.org's limit; longer messages are dropped
NAME_BUDGET = 20            # characters reserved for the {me} substitution


def render(era: str, source: Path = SRC) -> str:
    """Substitute this era's identity into the config template."""
    era_cfg = CFG["eras"][era]
    years = era_cfg.get("years", [])
    text = source.read_text()
    text = text.replace("%ERA_NAME%", era_cfg.get("name", era))
    text = text.replace("%ERA_YEARS%", f"{years[0]}-{years[1]}" if len(years) == 2 else "")
    return text


def check_greetings(text: str) -> list:
    """Return a list of complaints about greeting lines that Lichess would drop."""
    problems = []
    for line in text.splitlines():
        stripped = line.strip()
        for key in ("hello:", "goodbye:", "hello_spectators:", "goodbye_spectators:"):
            if stripped.startswith(key):
                message = stripped[len(key):].strip().strip('"')
                budget = MAX_CHAT_LEN - (NAME_BUDGET if "{me}" in message else 0)
                if len(message) > budget:
                    problems.append(
                        f"{key[:-1]} is {len(message)} characters (limit {budget}"
                        + (" with room for {me}" if "{me}" in message else "")
                        + "); Lichess would drop it silently")
    return problems


def main(argv: list) -> int:
    era = era_from_env()
    dest = Path(argv[1]) if len(argv) > 1 else Path("config.yml")
    text = render(era)

    problems = check_greetings(text)
    if problems:
        for p in problems:
            print(f"[config] {p}", file=sys.stderr)
        return 1

    if not os.environ.get("LICHESS_BOT_TOKEN"):
        print("[config] LICHESS_BOT_TOKEN is not set — lichess-bot will try the "
              "placeholder token in config.yml and be rejected by Lichess.",
              file=sys.stderr)
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    print(f"[config] {era} ({CFG['eras'][era].get('name', era)}) -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
