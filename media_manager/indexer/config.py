from pydantic import Field
from pydantic_settings import BaseSettings


class ProwlarrConfig(BaseSettings):
    enabled: bool = False
    api_key: str = ""
    url: str = "http://localhost:9696"
    timeout_seconds: int = 60
    max_results: int = Field(default=1000, ge=1, le=1000)


class JackettConfig(BaseSettings):
    enabled: bool = False
    api_key: str = ""
    url: str = "http://localhost:9117"
    indexers: list[str] = ["all"]
    timeout_seconds: int = 60
    max_results: int = Field(default=1000, ge=1, le=1000)


class ScoringRule(BaseSettings):
    name: str
    score_modifier: int = 0
    negate: bool = False


class TitleScoringRule(ScoringRule):
    keywords: list[str]


class IndexerFlagScoringRule(ScoringRule):
    flags: list[str]


class ScoringRuleSet(BaseSettings):
    name: str
    libraries: list[str] = []
    rule_names: list[str] = []


class IndexerConfig(BaseSettings):
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    jackett: JackettConfig = JackettConfig()
    title_scoring_rules: list[TitleScoringRule] = []
    indexer_flag_scoring_rules: list[IndexerFlagScoringRule] = []
    scoring_rule_sets: list[ScoringRuleSet] = []
