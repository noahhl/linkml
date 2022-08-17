import inspect
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

import yaml
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SchemaDefinition

from .config.datamodel.config import Config, RuleConfig, RuleLevel


@dataclass
class LinterProblem:
    message: str
    level: Union[RuleLevel, None] = None
    schema_name: Union[str, None] = None
    schema_source: Union[str, None] = None
    rule_name: Union[str, None] = None


class LinterRule(ABC):
    def __init__(self, config: RuleConfig) -> None:
        super().__init__()
        self.config = config

    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    def check(self, schema_view: SchemaView, fix: bool) -> Iterable[LinterProblem]:
        pass


@lru_cache
def get_default_config() -> Dict[str, Any]:
    config_path = str(Path(__file__).parent / "config/default.yaml")
    with open(config_path) as config_file:
        return yaml.safe_load(config_file)


def merge_configs(original: dict, other: dict):
    result = deepcopy(original)
    for key, value in other.items():
        if isinstance(value, dict):
            result[key] = merge_configs(result.get(key, {}), value)
        else:
            result[key] = value
    return result


class Linter:
    def __init__(self, config: Dict[str, Any] = {}) -> None:
        default_config = deepcopy(get_default_config())
        merged_config = merge_configs(default_config, config)
        self.config = Config(**merged_config)

        from . import rules

        self._rules_map = dict(
            [
                (cls.id, cls)
                for _, cls in inspect.getmembers(rules, inspect.isclass)
                if issubclass(cls, LinterRule)
            ]
        )

    def lint(
        self, schema=Union[str, SchemaDefinition], fix: bool = False
    ) -> List[LinterProblem]:
        schema_view = SchemaView(schema)
        report = []
        for rule_id, rule_config in self.config.__dict__.items():
            rule_cls = self._rules_map.get(rule_id, None)
            if rule_cls is None:
                raise ValueError("Unknown rule id: " + rule_id)

            rule = rule_cls(rule_config)

            if str(rule.config.level) is RuleLevel.disabled.text:
                continue

            for problem in rule.check(schema_view, fix=fix):
                problem.level = rule.config.level
                problem.rule_name = rule.id
                problem.schema_name = schema_view.schema.name
                if isinstance(schema, str):
                    problem.schema_source = schema
                report.append(problem)

        return report
