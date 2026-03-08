from libsrc.git import match_version_tag


class TestExactMatches:
    def test_v_prefix(self):
        assert match_version_tag(["v1.2.3", "v1.2.2"], "1.2.3") == "v1.2.3"

    def test_bare_version(self):
        assert match_version_tag(["1.2.3", "1.2.2"], "1.2.3") == "1.2.3"

    def test_release_prefix(self):
        assert match_version_tag(["release-1.2.3"], "1.2.3") == "release-1.2.3"

    def test_artifact_id_prefix(self):
        assert (
            match_version_tag(
                ["hibernate-core-6.4.1", "other-6.4.1"],
                "6.4.1",
                artifact_id="hibernate-core",
            )
            == "hibernate-core-6.4.1"
        )

    def test_v_prefix_preferred_over_bare(self):
        tags = ["v1.2.3", "1.2.3"]
        assert match_version_tag(tags, "1.2.3") == "v1.2.3"

    def test_bare_preferred_over_release(self):
        tags = ["1.2.3", "release-1.2.3"]
        assert match_version_tag(tags, "1.2.3") == "1.2.3"


class TestReleaseQualifierStripping:
    def test_dot_final(self):
        tags = ["6.6.39"]
        assert match_version_tag(tags, "6.6.39.Final") == "6.6.39"

    def test_dot_release(self):
        tags = ["v5.3.20"]
        assert match_version_tag(tags, "5.3.20.RELEASE") == "v5.3.20"

    def test_dot_ga(self):
        tags = ["v2.0.0"]
        assert match_version_tag(tags, "2.0.0.GA") == "v2.0.0"

    def test_hyphen_final(self):
        tags = ["3.1.0"]
        assert match_version_tag(tags, "3.1.0-Final") == "3.1.0"

    def test_hyphen_release(self):
        tags = ["v4.0.0"]
        assert match_version_tag(tags, "4.0.0-RELEASE") == "v4.0.0"

    def test_hyphen_ga(self):
        tags = ["1.0.0"]
        assert match_version_tag(tags, "1.0.0-GA") == "1.0.0"

    def test_original_version_preferred_over_stripped(self):
        """If the tag with the qualifier exists, prefer it over the stripped one."""
        tags = ["6.6.39.Final", "6.6.39"]
        assert match_version_tag(tags, "6.6.39.Final") == "6.6.39.Final"

    def test_v_prefix_with_stripped_qualifier(self):
        tags = ["v6.6.39"]
        assert match_version_tag(tags, "6.6.39.Final") == "v6.6.39"


class TestSuffixMatches:
    def test_suffix_match(self):
        tags = ["spring-boot-3.2.1", "other-tag"]
        assert match_version_tag(tags, "3.2.1") == "spring-boot-3.2.1"

    def test_shorter_suffix_preferred(self):
        tags = ["spring-boot-starter-3.2.1", "boot-3.2.1"]
        assert match_version_tag(tags, "3.2.1") == "boot-3.2.1"


class TestContainsMatches:
    def test_contains_match(self):
        tags = ["rel/v1.2.3-rc1", "1.2.3-beta"]
        # "1.2.3" is contained in both; shorter wins
        assert match_version_tag(tags, "1.2.3") == "1.2.3-beta"

    def test_shorter_contains_preferred(self):
        tags = ["prefix-1.2.3-suffix", "x-1.2.3-y"]
        assert match_version_tag(tags, "1.2.3") == "x-1.2.3-y"


class TestNoMatch:
    def test_no_matching_tag(self):
        tags = ["v2.0.0", "v3.0.0"]
        assert match_version_tag(tags, "1.0.0") is None

    def test_empty_tags(self):
        assert match_version_tag([], "1.0.0") is None


class TestRealWorldCases:
    def test_hibernate_core(self):
        """Hibernate uses bare version tags without the .Final suffix."""
        tags = ["6.6.38", "6.6.39", "6.6.40"]
        assert match_version_tag(tags, "6.6.39.Final") == "6.6.39"

    def test_spring_framework(self):
        tags = ["v6.1.0", "v6.1.1", "v6.1.2"]
        assert match_version_tag(tags, "6.1.2") == "v6.1.2"

    def test_jackson(self):
        """Jackson uses artifact-prefixed tags."""
        tags = [
            "jackson-databind-2.17.0",
            "jackson-databind-2.17.1",
            "jackson-core-2.17.0",
        ]
        assert (
            match_version_tag(tags, "2.17.1", artifact_id="jackson-databind")
            == "jackson-databind-2.17.1"
        )

    def test_guava(self):
        tags = ["v33.0.0", "v33.1.0", "v33.2.0"]
        assert match_version_tag(tags, "33.1.0") == "v33.1.0"

    def test_slf4j(self):
        tags = ["v_2.0.9", "v_2.0.10", "v_2.0.11"]
        # "2.0.10" doesn't match v_ prefix exactly, falls to suffix match
        assert match_version_tag(tags, "2.0.10") == "v_2.0.10"
