import pytest

from mcpmaker.auth import PassThroughAuth, parse_header


def test_forwards_authorization_and_cookie_case_insensitively():
    auth = PassThroughAuth()
    incoming = {"Authorization": "Bearer t", "cookie": "s=1", "host": "x", "content-length": "5"}
    assert auth.headers_for(incoming) == {"authorization": "Bearer t", "cookie": "s=1"}


def test_forwards_extra_headers():
    auth = PassThroughAuth(["X-API-Key"])
    assert auth.headers_for({"x-api-key": "k", "x-other": "o"}) == {"x-api-key": "k"}


def test_missing_headers_are_not_invented():
    assert PassThroughAuth().headers_for({}) == {}


def test_parse_header():
    assert parse_header("Authorization: Bearer a:b") == ("Authorization", "Bearer a:b")
    assert parse_header("  X-Key :  v  ") == ("X-Key", "v")


@pytest.mark.parametrize("raw", ["no-colon", ": value", ""])
def test_parse_header_rejects_bad_input(raw):
    with pytest.raises(ValueError, match="Name: value"):
        parse_header(raw)


def test_parse_header_error_never_echoes_the_raw_value():
    import pytest
    from mcpmaker.auth import parse_header

    with pytest.raises(ValueError, match="Name: value") as info:
        parse_header("Bearer leakme123")
    assert "leakme123" not in str(info.value)
