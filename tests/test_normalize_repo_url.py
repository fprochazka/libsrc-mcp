from libsrc.source_resolver import normalize_repo_url


class TestHttpsUrls:
    def test_github_https(self):
        result = normalize_repo_url("https://github.com/owner/repo")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_gitlab_https(self):
        result = normalize_repo_url("https://gitlab.com/owner/repo")
        assert result == ("gitlab.com", "https://gitlab.com/owner/repo")

    def test_strips_dot_git(self):
        result = normalize_repo_url("https://github.com/owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_strips_tree_path(self):
        result = normalize_repo_url("https://github.com/owner/repo/tree/main/subdir")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_http_url(self):
        result = normalize_repo_url("http://github.com/owner/repo")
        assert result == ("github.com", "https://github.com/owner/repo")


class TestGitAtUrls:
    def test_git_at_github(self):
        result = normalize_repo_url("git@github.com:owner/repo")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_git_at_with_dot_git(self):
        result = normalize_repo_url("git@github.com:owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")


class TestScmPrefixes:
    def test_scm_git_prefix(self):
        result = normalize_repo_url("scm:git:https://github.com/owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_scm_git_at(self):
        result = normalize_repo_url("scm:git:git@github.com:owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_scm_svn_prefix(self):
        result = normalize_repo_url("scm:svn:https://github.com/owner/repo")
        assert result == ("github.com", "https://github.com/owner/repo")


class TestGitProtocol:
    def test_git_protocol(self):
        result = normalize_repo_url("git://github.com/owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")


class TestSshUrls:
    def test_ssh_git_at(self):
        result = normalize_repo_url("ssh://git@github.com/owner/repo.git")
        assert result == ("github.com", "https://github.com/owner/repo")


class TestEdgeCases:
    def test_empty_string(self):
        assert normalize_repo_url("") is None

    def test_whitespace(self):
        result = normalize_repo_url("  https://github.com/owner/repo  ")
        assert result == ("github.com", "https://github.com/owner/repo")

    def test_not_a_url(self):
        assert normalize_repo_url("not a url") is None

    def test_single_path_segment(self):
        assert normalize_repo_url("https://example.com/only-one") is None
