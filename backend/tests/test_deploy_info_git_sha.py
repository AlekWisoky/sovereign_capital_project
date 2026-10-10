from victor_ai_bot.runtime_services.runtime_routes_service import RuntimeRoutesService


def test_deploy_info_reports_stamped_git_sha_and_private_safety(monkeypatch):
    expected_sha = "a" * 40
    monkeypatch.setenv("VICTOR_GIT_SHA", expected_sha)
    monkeypatch.setenv("VICTOR_DEPLOYMENT_MODE", "private")
    monkeypatch.delenv("VICTOR_PUBLIC_ALLOW_BROADCAST", raising=False)

    payload = RuntimeRoutesService().deploy_info()

    assert payload["git_sha"] == expected_sha
    assert payload["mode"] == "private"
    assert payload["public_mode"] is False
    assert payload["public_allow_broadcast"] is False


def test_deploy_info_fails_closed_to_unknown_when_sha_is_missing(monkeypatch):
    monkeypatch.delenv("VICTOR_GIT_SHA", raising=False)

    payload = RuntimeRoutesService().deploy_info()

    assert payload["git_sha"] == "unknown"
