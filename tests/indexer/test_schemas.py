# ruff: noqa: S101

from media_manager.indexer.schemas import IndexerQueryResult


def make_result(title: str) -> IndexerQueryResult:
    return IndexerQueryResult(
        title=title,
        download_url="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
        seeders=1,
        flags=[],
        size=1,
        usenet=False,
        age=0,
        indexer="test",
    )


def test_newer_usenet_release_is_preferred() -> None:
    newer = make_result("Example.Show.S01E01.1080p")
    newer.usenet = True
    newer.age = 60
    older = make_result("Example.Show.S01E01.1080p")
    older.usenet = True
    older.age = 3_600

    assert sorted([older, newer], reverse=True)[0] is newer


def test_parses_x_notation_episode() -> None:
    result = make_result("Example Show 2x07 1080p")

    assert result.season == [2]
    assert result.episode == [7]


def test_parses_repeated_e_episode_range() -> None:
    result = make_result("Example.Show.S03E04E06.2160p")

    assert result.season == [3]
    assert result.episode == [4, 5, 6]


def test_parses_explicit_e_episode_range() -> None:
    result = make_result("Example.Show.S03E04-E06.2160p")

    assert result.season == [3]
    assert result.episode == [4, 5, 6]


def test_parses_dotted_episode_without_treating_it_as_a_season_pack() -> None:
    result = make_result("Example.Show.S01.E03.1080p")

    assert result.season == [1]
    assert result.episode == [3]


def test_parses_spaced_episode_without_treating_it_as_a_season_pack() -> None:
    result = make_result("Example Show S02 E07 2160p")

    assert result.season == [2]
    assert result.episode == [7]


def test_parses_dotted_multi_episode_release() -> None:
    result = make_result("Example.Show.S04.E05.E06.1080p")

    assert result.season == [4]
    assert result.episode == [5, 6]
