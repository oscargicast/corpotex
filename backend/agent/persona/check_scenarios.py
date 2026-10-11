"""Run the prompt scenarios in `scenarios.yaml` against the real model.

    python -m agent.persona.check_scenarios --list
    python -m agent.persona.check_scenarios --run [--p0] [name ...]

Runs with the connected Claude account and spends the subscription: run it by hand, never
during the demo. In test mode the model gets no tools; it writes `MENSAJE:` and `TOOL:` lines
instead, which is enough to check wording and which tools it would call.
"""

import argparse
import asyncio
import copy
import os
import re
import sys
from pathlib import Path

import yaml

from . import prompt as whatsapp_prompt
from .style import load_template

SCENARIOS_PATH = Path(__file__).parent / "scenarios.yaml"

TEST_PROTOCOL = """\
<modo_prueba>
Esto es una prueba: no tienes tools. Escribe solo lo que harías, una acción por línea:
- por cada mensaje que mandarías: MENSAJE: <texto>
- por cada tool que usarías: TOOL: <nombre> <argumentos en JSON>
Nada más.
</modo_prueba>"""

ASSISTANT_TEST_PROTOCOL = """\
<modo_prueba>
Esto es una prueba: no tienes tools. Escribe solo lo que harías, una acción por línea:
- por cada tool que usarías: TOOL: <nombre> <argumentos en JSON>
- tu respuesta al usuario, al final: RESPUESTA: <texto> (puede seguir en varias líneas)
Nada más.
</modo_prueba>"""


def deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = []
    for scenario in data["scenarios"]:
        state = deep_merge(data["defaults"][scenario["agent"]], scenario.get("state") or {})
        if state.get("style_md") == "@template":
            state["style_md"] = load_template()
        scenarios.append({**scenario, "state": state})
    return scenarios


def parse_output(text: str, agent: str) -> tuple[list[str], list[str]]:
    """`(messages, tools)` from the test-mode output."""
    messages, tools, answer = [], [], []
    in_answer = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("TOOL:"):
            parts = stripped[5:].split(maxsplit=1)
            if parts:
                tools.append(parts[0])
            in_answer = False
        elif stripped.startswith("MENSAJE:"):
            messages.append(stripped[8:].strip())
            tools.append("send_message")  # in test mode each message stands for that tool
            in_answer = False
        elif stripped.startswith("RESPUESTA:"):
            answer = [stripped[10:].strip()]
            in_answer = True
        elif in_answer:
            answer.append(line)
    if agent == "assistant" and answer:
        messages = ["\n".join(answer).strip()]
    return messages, tools


def check(scenario: dict, messages: list[str], tools: list[str]) -> list[str]:
    """Failures of one scenario run; empty means it passed."""
    failures = []
    joined = "\n".join(messages)
    for pattern in scenario.get("must") or []:
        if not re.search(pattern, joined, re.IGNORECASE | re.MULTILINE):
            failures.append(f"falta /{pattern}/")
    for pattern in scenario.get("must_not") or []:
        if re.search(pattern, joined, re.IGNORECASE | re.MULTILINE):
            failures.append(f"aparece /{pattern}/")
    for tool in scenario.get("expect_tools") or []:
        if tool not in tools:
            failures.append(f"no usó {tool}")
    for tool in scenario.get("forbid_tools") or []:
        if tool in tools:
            failures.append(f"usó {tool}")
    limit = scenario.get("max_messages")
    if limit and len(messages) > limit:
        failures.append(f"{len(messages)} mensajes (máximo {limit})")
    suffix = scenario.get("ends_with")
    if suffix and not (messages and messages[-1].rstrip().endswith(suffix)):
        failures.append(f'no termina en "{suffix}"')
    return failures


def build(scenario: dict) -> tuple[str, str] | None:
    """`(system, prompt)` in test mode, or None if that agent's prompt is not built yet."""
    state = scenario["state"]
    if scenario["agent"] == "whatsapp":
        system = whatsapp_prompt.render_system(_rules("RULES"), state)
        blocks = whatsapp_prompt.render_turn_message(state)
        return system, blocks[0]["text"] + "\n\n" + TEST_PROTOCOL
    try:
        from . import assistant
    except ImportError:
        return None
    system = assistant.render_system(_rules("ASSISTANT_RULES"), state)
    blocks = assistant.render_turn_message(state)
    return system, blocks[0]["text"] + "\n\n" + ASSISTANT_TEST_PROTOCOL


def _rules(name: str) -> str:
    try:
        from agent import rules
    except ImportError:
        return f"({name} de agent/rules.py todavía no existe)"
    return getattr(rules, name, f"({name} todavía no existe)")


def _complete(system: str, prompt: str) -> str:
    from agent import sdk

    model = os.environ.get("AGENT_MODEL", "sonnet")
    return asyncio.run(sdk.complete(prompt, system_prompt=system, model=model))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    parser.add_argument("--run", action="store_true", help="run against the real model")
    parser.add_argument("--p0", action="store_true", help="only P0 scenarios")
    parser.add_argument("names", nargs="*", help="run only these scenarios")
    args = parser.parse_args(argv)

    scenarios = load_scenarios()
    if args.p0:
        scenarios = [s for s in scenarios if s.get("priority", "P0") == "P0"]
    if args.names:
        scenarios = [s for s in scenarios if s["name"] in args.names]

    if args.list or not args.run:
        for scenario in scenarios:
            print(f"{scenario['name']:45} {scenario['agent']:10} {scenario.get('priority', 'P0')}")
        print(f"{len(scenarios)} escenarios")
        return 0

    if os.environ.get("DJANGO_SETTINGS_MODULE"):
        import django

        django.setup()

    failed = 0
    for scenario in scenarios:
        built = build(scenario)
        if built is None:
            print(f"SALTA  {scenario['name']}: falta el prompt de {scenario['agent']}")
            continue
        output = _complete(*built)
        messages, tools = parse_output(output, scenario["agent"])
        failures = check(scenario, messages, tools)
        status = "PASA " if not failures else "FALLA"
        failed += bool(failures)
        print(f"{status}  {scenario['name']}  tools={tools}")
        for message in messages:
            print(f"         > {message}")
        for failure in failures:
            print(f"         ! {failure}")
    print(f"{len(scenarios) - failed} de {len(scenarios)} pasan")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
