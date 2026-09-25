import logging
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from media_manager.config import MediaManagerConfig
from media_manager.indexer.config import ScoringRuleSet
from media_manager.indexer.schemas import IndexerQueryResult
from media_manager.movies.schemas import Movie
from media_manager.tv.schemas import Show

log = logging.getLogger(__name__)


def sanitize_url_for_logging(url: str) -> str:
    """Return only a URL's scheme, host, port and path for safe diagnostics."""
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = parsed.port
    except (UnicodeError, ValueError):
        return "<invalid-url>"

    netloc = hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path or ("/" if netloc else "")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")
_SECRET_PARAMETER_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|apikey|passkey|token|password|secret)=([^&\s'\"]+)"
)


def redact_secrets(text: str) -> str:
    """Strip URL queries, URL credentials and key=value secrets from free text.

    Exception messages from HTTP clients often embed the full request URL,
    which for Jackett and many trackers includes an API key or passkey.
    """
    text = _URL_PATTERN.sub(
        lambda match: sanitize_url_for_logging(match.group(0)), text
    )
    return _SECRET_PARAMETER_PATTERN.sub(lambda match: f"{match.group(1)}=***", text)


def evaluate_indexer_query_result(
    query_result: IndexerQueryResult, ruleset: ScoringRuleSet
) -> tuple[IndexerQueryResult, bool]:
    title_rules = MediaManagerConfig().indexers.title_scoring_rules
    indexer_flag_rules = MediaManagerConfig().indexers.indexer_flag_scoring_rules
    for rule_name in ruleset.rule_names:
        for rule in title_rules:
            if rule.name == rule_name:
                log.debug(f"Applying rule {rule.name} to {query_result.title}")
                if (
                    any(
                        re.search(
                            rf"\b{re.escape(keyword)}\b",
                            query_result.title,
                            re.IGNORECASE,
                        )
                        for keyword in rule.keywords
                    )
                    and not rule.negate
                ):
                    log.debug(
                        f"Rule {rule.name} with keywords {rule.keywords} matched for {query_result.title}"
                    )
                    query_result.score += rule.score_modifier
                elif (
                    not any(
                        re.search(
                            rf"\b{re.escape(keyword)}\b",
                            query_result.title,
                            re.IGNORECASE,
                        )
                        for keyword in rule.keywords
                    )
                    and rule.negate
                ):
                    log.debug(
                        f"Negated rule {rule.name} with keywords {rule.keywords} matched for {query_result.title}"
                    )
                    query_result.score += rule.score_modifier
                else:
                    log.debug(
                        f"Rule {rule.name} with keywords {rule.keywords} did not match for {query_result.title}"
                    )
        for rule in indexer_flag_rules:
            if rule.name == rule_name:
                log.debug(f"Applying rule {rule.name} to {query_result.title}")
                if (
                    any(flag in query_result.flags for flag in rule.flags)
                    and not rule.negate
                ):
                    log.debug(
                        f"Rule {rule.name} with flags {rule.flags} matched for {query_result.title} with flags {query_result.flags}"
                    )
                    query_result.score += rule.score_modifier
                elif (
                    not any(flag in query_result.flags for flag in rule.flags)
                    and rule.negate
                ):
                    log.debug(
                        f"Negated rule {rule.name} with flags {rule.flags} matched for {query_result.title} with flags {query_result.flags}"
                    )
                    query_result.score += rule.score_modifier
                else:
                    log.debug(
                        f"Rule {rule.name} with flags {rule.flags} did not match for {query_result.title} with flags {query_result.flags}"
                    )
    if query_result.score <= 0:
        return query_result, False

    return query_result, True


def evaluate_indexer_query_results(
    query_results: list[IndexerQueryResult], media: Show | Movie, is_tv: bool
) -> list[IndexerQueryResult]:
    scoring_rulesets: list[ScoringRuleSet] = (
        MediaManagerConfig().indexers.scoring_rule_sets
    )
    for ruleset in scoring_rulesets:
        if (
            (media.library in ruleset.libraries)
            or ("ALL_TV" in ruleset.libraries and is_tv)
            or ("ALL_MOVIES" in ruleset.libraries and not is_tv)
        ):
            log.debug(
                f"Applying scoring ruleset {ruleset.name} for {media.name} ({media.year}) to {len(query_results)} results."
            )
            for result in query_results:
                log.debug(
                    f"Applying scoring ruleset {ruleset.name} for IndexerQueryResult {result.title} for {media.name} ({media.year})"
                )
                result, passed = evaluate_indexer_query_result(
                    query_result=result, ruleset=ruleset
                )
                if not passed:
                    log.debug(
                        f"Indexer query result {result.title} did not pass scoring ruleset {ruleset.name} with score {result.score}, removing from results."
                    )
                else:
                    log.debug(
                        f"Indexer query result {result.title} passed scoring ruleset {ruleset.name} with score {result.score}."
                    )

    query_results = [result for result in query_results if result.score >= 0]
    query_results.sort(reverse=True)
    log.info(f"{len(query_results)} passed the scoring rulesets")
    return query_results


def follow_redirects_to_final_torrent_url(
    initial_url: str, session: requests.Session, timeout: float = 10
) -> str:
    """
    Follows redirects to get the final torrent URL.
    :param initial_url: The initial URL to follow.
    :param session: A requests session to use for the requests.
    :param timeout: Timeout in seconds for each redirect request.
    :return: The final torrent URL.
    :raises: RuntimeError if it fails.
    """
    current_url = initial_url
    try:
        for _ in range(10):  # Limit redirects to prevent infinite loops
            response = session.get(current_url, allow_redirects=False, timeout=timeout)

            if 300 <= response.status_code < 400:
                redirect_url = response.headers.get("Location")
                if not redirect_url:
                    msg = "Redirect response without Location header"
                    raise RuntimeError(msg)

                # Resolve relative redirects against the last URL
                current_url = urljoin(current_url, redirect_url)
                log.debug(
                    "Following redirect to %s",
                    sanitize_url_for_logging(current_url),
                )

                if current_url.startswith("magnet:"):
                    return current_url
            else:
                response.raise_for_status()  # Raise an exception for bad status codes
                return current_url
        else:
            msg = "Exceeded maximum number of redirects"
            raise RuntimeError(msg)

    except requests.exceptions.RequestException as error:
        log.debug(
            "Request to %s failed (%s)",
            sanitize_url_for_logging(initial_url),
            type(error).__name__,
        )
        msg = "An error occurred during the request"
        # The requests exception can contain the full URL. Suppressing the cause
        # prevents callers that log this RuntimeError from exposing its secrets.
        raise RuntimeError(msg) from None
