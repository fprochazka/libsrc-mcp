# Technical Research Report: Programmatic Dependency Resolution and Source Extraction in Python uv Projects

## Executive Summary
For the development of a tool capable of programmatically resolving dependency trees and locating source code repositories within `uv`-managed Python projects, the optimal strategy requires a hybrid approach. While `uv` provides Command Line Interface (CLI) utilities for human-readable output (`uv tree`), the most robust programmatic method involves two distinct steps: (1) parsing the `uv.lock` file or exporting to the CycloneDX JSON format to construct the exact resolution graph, and (2) querying the PyPI JSON API to retrieve metadata such as source code repository URLs, which are not intrinsically stored in the lockfile for registry-based packages.

The `uv.lock` file is a universal, cross-platform TOML file that creates a deterministic graph including all possible resolution "forks" (platform-specific branches). Parsing this directly provides the highest fidelity. Alternatively, `uv export --format cyclonedx` offers a standardized JSON output that requires less custom parsing logic but may abstract away some `uv`-specific internal mechanics like resolution markers. `uv pip list --format json` provides a flat inventory of the current environment but lacks the hierarchical data necessary for a dependency tree.

**Key Technical Recommendations:**
*   **Primary Data Source:** Parse `uv.lock` (TOML) for the complete dependency graph, version pinning, and source origins (Git/Registry/Path).
*   **Alternative Data Source:** Use `uv export --format cyclonedx1.5 --output-file sbom.json` for a standards-compliant JSON graph.
*   **Metadata Enrichment:** Use the PyPI JSON API (`https://pypi.org/pypi/<package>/json`) to resolve `project_urls` for finding source repositories (e.g., GitHub, GitLab).
*   **Workspace Handling:** Process the root `uv.lock` which aggregates all workspace members, identifying local packages via `source = { workspace = true }` or `source = { virtual = "." }`.

---

## 1. CLI Commands for Dependency Extraction

`uv` offers several commands to inspect dependencies. For programmatic tooling, the choice of command depends on whether the goal is to inspect the *current environment* or the *abstract dependency graph* defined in the lockfile.

### 1.1 `uv pip list`
This command lists packages installed in the currently active virtual environment.

*   **Invocation:** `uv pip list --format json`
*   **Output Format:** A JSON array of objects.
*   **Fields:** `name`, `version`.
*   **Use Case:** Inventory validation of what is physically installed.
*   **Limitations:** It produces a flat list, not a tree. It does not show relationships between parents and children [cite: 1, 2].

### 1.2 `uv tree`
This command visualizes the dependency tree for the project.

*   **Invocation:** `uv tree`
*   **Output Format:** Currently, `uv tree` outputs a human-readable text tree structure.
*   **JSON Support:** As of current versions, `uv tree` **does not** support JSON output (`--format json`), though this feature has been requested and discussed in issue trackers [cite: 2, 3, 4].
*   **Arguments:**
    *   `--universal`: Shows the dependency tree for all environments/platforms (universal resolution) rather than just the current platform [cite: 3].
    *   `--depth <N>`: Limits tree depth.
    *   `--invert`: Shows reverse dependencies (dependents) [cite: 3].
*   **Utility:** Useful for debugging but requires brittle text parsing for programmatic use; therefore, it is **not recommended** for building reliable tools.

### 1.3 `uv pip freeze`
This command outputs installed packages in a standard requirements format.

*   **Invocation:** `uv pip freeze`
*   **Output Format:** Standard `requirements.txt` format (`package==version`).
*   **JSON Support:** Does not support JSON output directly.
*   **Utility:** Useful for generating snapshots for legacy tools but lacks graph structure metadata [cite: 5].

### 1.4 `uv export` (Recommended for JSON)
The `export` command is the most powerful interface for external tools because it can convert the internal `uv.lock` into standardized formats.

*   **Invocation:** `uv export --format cyclonedx1.5 --output-file dependency-graph.json`
*   **Output Format:** CycloneDX v1.5 JSON.
*   **Utility:** This generates a structured Software Bill of Materials (SBOM) containing component hierarchies, versions, and sources. It avoids the need to write a custom TOML parser for `uv.lock` if standard compliance is preferred [cite: 6].
*   **Arguments:**
    *   `--no-dev`: Exclude development dependencies.
    *   `--frozen`: Do not update `uv.lock`; fail if it is outdated.
    *   `--format requirements.txt`: Outputs standard requirements file [cite: 6].
    *   `--format pylock.toml`: Outputs PEP 751 standardized lockfile (currently insufficient to replace `uv.lock` features completely) [cite: 6, 7].

---

## 2. Parsing `uv.lock`: Structure and Fields

The `uv.lock` file is the source of truth for the project's dependency resolution. It is a TOML file maintained by `uv`. For a tool builder, parsing this file directly yields the most granular data.

### 2.1 File Structure
The file generally consists of a header and a list of `[[package]]` tables.

```toml
version = 1
requires-python = ">=3.12"

[[package]]
name = "requests"
version = "2.32.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "certifi" },
    { name = "idna" },
    { name = "urllib3" },
]
sdist = { ... }
wheels = [ ... ]
```

### 2.2 Fields per `[[package]]` Entry
*   **`name`**: The normalized name of the package (e.g., "pandas") [cite: 8].
*   **`version`**: The specific locked version (e.g., "2.2.3") [cite: 8, 9].
*   **`source`**: A dictionary defining where the package comes from.
    *   **Registry:** `source = { registry = "https://pypi.org/simple" }`. Indicates a standard index installation [cite: 8].
    *   **Git:** `source = { git = "https://github.com/user/repo", revision = "..." }`. Used for git dependencies [cite: 10, 11].
    *   **Path/Editable:** `source = { virtual = "." }` or similar for the root project or workspace members installed in editable mode [cite: 12].
    *   **Workspace:** `source = { workspace = true }`. Indicates the package is a member of the current workspace [cite: 13].
*   **`dependencies`**: A list of objects representing direct dependencies. Each entry typically contains the `name` of the dependency. It may also contain marker information if the dependency is conditional [cite: 8].
*   **`optional-dependencies`**: Defines extras (e.g., `pandas[plot]`). These are listed if the extra was requested or resolved.
*   **`sdist`**: Metadata about the source distribution (tarball).
    *   Fields: `url`, `hash` (SHA256), `size` [cite: 8].
*   **`wheels`**: A list of available binary wheels for this version.
    *   Fields: `url`, `hash`, `size`. This allows verification of artifacts across different platforms [cite: 8, 14].

### 2.3 Multiple Versions and Forking
A unique feature of `uv` is that `uv.lock` is **universal**. It may contain multiple entries for the *same* package name if different versions are required for different platforms or Python versions. This is handled via the "forking" resolver.

*   **Duplicate Entries:** You may see multiple `[[package]]` blocks for `numpy`. One version might be for Python < 3.10 and another for Python >= 3.10.
*   **Resolution Markers:** To distinguish these, `uv` uses internal markers (though often implicit in the graph structure or explicit in `resolution-markers` in newer versions) to determine which entry applies to the current environment [cite: 15, 16, 17].

---

## 3. Parsing `pyproject.toml` for Dependencies

While `uv.lock` contains the *resolved* tree, `pyproject.toml` contains the *declared* constraints.

### 3.1 Standard PEP 621 Dependencies
`uv` adheres to PEP 621 for declaring dependencies in the `[project]` table.

*   **`[project.dependencies]`**: A list of strings defining direct runtime dependencies (e.g., `["requests>=2.31.0", "numpy"]`) [cite: 18, 19].
*   **`[project.optional-dependencies]`**: A table defining extras.
    *   Example: `plot = ["matplotlib"]`.
    *   These form the entry points for the resolution graph [cite: 19].

### 3.2 Dependency Groups (PEP 735)
`uv` uses `[dependency-groups]` for development dependencies, replacing the older `dev-dependencies` concept.

*   **Table:** `[dependency-groups]`
*   **Example:**
    ```toml
    [dependency-groups]
    dev = ["pytest", "ruff"]
    docs = ["mkdocs"]
    ```
*   **Note:** These are strictly for development and are not included in the published package metadata, but they *are* included in `uv.lock` so that dev environments are reproducible [cite: 20, 21].

### 3.3 `[tool.uv]` Overrides
`uv` allows source overrides in `pyproject.toml` which affect how dependencies are located.

*   **`[tool.uv.sources]`**: Maps package names to specific sources (Git, local path, or specific indexes).
    *   Example: `torch = { index = "torch-cpu" }` or `httpx = { git = "https://github.com/encode/httpx" }` [cite: 19].
    *   Your tool must parse this table to understand if a dependency declared in `[project.dependencies]` is actually being pulled from a non-standard location.

---

## 4. `uv export`: Interoperability Formats

The `uv export` command allows extracting the dependency state into standard formats. This is often easier than parsing TOML.

### 4.1 Requirements.txt
*   **Command:** `uv export --format requirements.txt`
*   **Content:** Standard pip format. It includes hashes and exact versions.
*   **Limitation:** It is a flat list. It flattens the tree, making it difficult to reconstruct which package brought in which transitive dependency [cite: 6].

### 4.2 CycloneDX (Recommended)
*   **Command:** `uv export --format cyclonedx1.5`
*   **Content:** A hierarchical JSON structure representing the Software Bill of Materials.
*   **Structure:** Includes a `components` array and a `dependencies` array (adjacency list).
*   **Adjacency List:** The `dependencies` section explicitly maps a component `ref` to its `dependsOn` list, allowing perfect reconstruction of the tree structure.
*   **Custom Fields:** `uv` adds custom properties like `uv:package:marker` and `uv:workspace:path` to the BOM components [cite: 6].

### 4.3 Pylock.toml (PEP 751)
*   **Command:** `uv export --format pylock.toml`
*   **Status:** `uv` supports exporting to this format, but the creators note that PEP 751 is currently insufficient to capture all of `uv`'s features (like specific cross-platform forks), so it is not used as the internal lockfile [cite: 6, 7].

---

## 5. Cross-Platform Resolution and Universal Lockfiles

`uv.lock` is designed to be universal, meaning it works on macOS, Linux, and Windows simultaneously.

### 5.1 Forking Mechanism
When a dependency graph diverges based on the platform (e.g., `torch` requires different wheels for Linux vs. Mac, or `numpy` versions differ by Python version), `uv` "forks" the resolution.

*   **Lockfile Representation:** You will see multiple `[[package]]` entries for the same package name.
*   **Selection Logic:** The resolver uses markers (e.g., `sys_platform == 'linux'`) to decide which branch of the fork to install.
*   **Tooling Implication:** A tool analyzing the tree must be aware that the graph is not a single DAG (Directed Acyclic Graph) but a superposition of multiple DAGs. To extract a concrete tree, the tool usually needs to simulate a specific environment (e.g., "What is the tree for Linux/Python 3.12?") or visualize all possibilities with conditional edges [cite: 16, 17, 22].

---

## 6. Finding Source Code Repositories

`uv.lock` and `pyproject.toml` primarily track **distribution** sources (where to get the installable artifact, e.g., a `.whl` from PyPI), not necessarily the **source code** repository (where the code lives, e.g., GitHub).

### 6.1 Strategy for Registry Packages (PyPI)
If `source = { registry = "..." }`, the lockfile gives you the package name and version. To find the source code:

1.  **Query PyPI JSON API:**
    *   Endpoint: `https://pypi.org/pypi/{package_name}/json` (or `.../{version}/json`).
2.  **Parse `info.project_urls`:**
    *   The API response contains a dictionary `project_urls` (from the package's metadata).
    *   **Keys to Search:** There is no enforced standard, but common keys include: `"Source"`, `"Source Code"`, `"Repository"`, `"GitHub"`, `"Code"`, `"Bug Tracker"` [cite: 23, 24].
    *   **Verification:** Check if the URL domain is a known forge (github.com, gitlab.com, bitbucket.org).

### 6.2 Strategy for Git Dependencies
If `source = { git = "..." }` in `uv.lock`:
*   The source code repository URL is explicitly available in the `git` field of the source object.
*   The `revision` or `tag` field indicates the specific commit [cite: 10].

---

## 7. Private and Custom Package Indexes

`uv` supports custom indexes, which changes how dependencies are resolved and represented.

### 7.1 Configuration
Custom indexes are defined in `pyproject.toml`:
```toml
[[tool.uv.index]]
name = "private-pypi"
url = "https://pypi.example.com/simple"
explicit = true  # If true, must be requested explicitly
```
[cite: 19, 25].

### 7.2 Lockfile Representation
In `uv.lock`, the `source` field reflects the specific index used for that package:
```toml
[[package]]
name = "my-private-lib"
source = { registry = "https://pypi.example.com/simple" }
```
A parsing tool should respect this URL rather than assuming `pypi.org`. If the URL is private, the tool may not be able to query a public JSON API for metadata and might need authentication or access to that specific private index's API [cite: 26, 27].

---

## 8. Workspace (Monorepo) Handling

`uv` workspaces allow multiple packages to share a single lockfile and environment.

### 8.1 Structure
*   **Root:** Contains `pyproject.toml` with `[tool.uv.workspace]`.
*   **Members:** Defined in `members = ["packages/*"]`.
*   **Lockfile:** One `uv.lock` at the root.

### 8.2 Dependency Resolution
*   **Shared Resolution:** All members are resolved together. Conflicting requirements between members are detected at lock time [cite: 13, 28].
*   **Local Dependencies:** If `package-a` depends on `package-b` (both in workspace), `uv.lock` represents `package-b` with a local path source or workspace source: `source = { workspace = true }`.
*   **Tooling Strategy:** To generate a tree for a *specific* member (e.g., just `package-a`), a tool must filter the graph. `uv export --package package-a` can help isolate the subgraph for a single member [cite: 29].

---

## 9. Differences vs. Pip and Poetry

*   **Performance:** `uv` is significantly faster due to its Rust implementation and global caching [cite: 30, 31].
*   **Lockfile:** `uv` uses a universal lockfile (like Poetry) but with a different internal structure (forking vs. separate constraints). Pip (via `pip-compile`) typically generates platform-specific `requirements.txt` files [cite: 14, 32].
*   **Resolution:** `uv` creates a single graph that satisfies *all* target platforms (forking), whereas pip resolves for the *current* platform. Poetry also creates universal locks but has faced performance issues with complex graphs that `uv` solves via PubGrub optimization [cite: 14, 17].
*   **Output:** `uv export` is required to get standard formats; `uv.lock` is not intended for consumption by other tools [cite: 32].

---

## 10. Editable Installs and Path Dependencies

### 10.1 Editable Installs
*   **Definition:** Packages installed with `-e .` or listed in `tool.uv.sources` with `editable = true`.
*   **Lockfile:** Represented with `source = { editable = "." }` or `source = { virtual = "." }`.
*   **Implication:** The code is read directly from the disk path. A source extraction tool should identify these as "local" and use the file system path provided in the lockfile rather than querying a registry [cite: 12].

### 10.2 Path Dependencies
*   **Definition:** Dependencies pointing to a local directory (e.g., `foo = { path = "./lib/foo" }`).
*   **Lockfile:** Explicitly records the path.
*   **Parsing:** The tool must resolve relative paths relative to the `uv.lock` file location [cite: 19].

---

## Summary of Actionable Steps for Tool Implementation

1.  **Detect `uv`:** Check for `uv.lock` and `pyproject.toml`.
2.  **Generate Graph:**
    *   *Preferably:* Run `uv export --format cyclonedx1.5 --output-file temp.json`. Parse JSON to build the dependency tree (Parent -> Children).
    *   *Alternatively:* Parse `uv.lock` (TOML). Map `[[package]]` entries. Link dependencies by name. Handle `source` fields to distinguish registry vs. git vs. workspace.
3.  **Resolve Source Code URLs:**
    *   Iterate through all packages in the graph.
    *   **If Registry:** Call `GET https://pypi.org/pypi/{name}/json`. Extract `info.project_urls` -> Look for "Source" or "GitHub".
    *   **If Git:** Extract URL from `source.git` field in lock/export.
    *   **If Path/Workspace:** Source is local; record the file path.
4.  **Handle Monorepos:** If `[tool.uv.workspace]` exists, allow the user to specify a target package (member) and filter the graph to include only that member's subgraph.

**Sources:**
1. [Link](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEfsj1aLQp5cV2e0WD_GKcpz6gYE4bDmJoQ5LonieyK11aF1TAUR7k-YN7CImRXwflcjqFc7hOEW9sw4g4MI6w493gO3VXj59ypHkub2DxCmwQoAZJIHNCiFwJi_nYhLGHrR7Q2CXx88hg=)
2. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFdfytfHq7QE033IRRUJt3nxdY-iucncT0igEsiztzk1vmF-Sb1rfN-3zCEg4MeRGDYRZMhAHYRhDvrWqP9kpAMN5jyQJ8jZDOPe8ualGSulbuDvtTHC56wPikKk-8REOuO)
3. [Link](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFejr7kcGKxB6tfxE8fqLtc0OeVjPd3jtVlMv1kPlGuNkMfXMLNRx_q7Jxi7rpmuCqhtpzkUbU06erHuQ328aY1EU7TfiJnbMpqTn4-V1LX347FQrP_NtZM0Xel0NZlIA79PB6mGw==)
4. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHefYHEDKiT1gylQGcGzRUp2ki3H4wsU09-iSP3CaBEv7hrn43cotHdSCM4HJitAoi72ptlWdjwTn9QUsE6r3L-CKlMYMwKjkOSdPHq9encvwwWxn6SYFrSQKcoIrhxvqpQ)
5. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEnQp0Yl0f4HFA7qLqxg_eM_nIDovEnyXzZ9b3mzyLP1UcKNoGDoiAJIKQ_RVmy5H7Jyr6Dkrc3UlN4lGbPttQ6AtVbWn9-HQhz5pZYaZEYl6reA31_q2qW3xHCWsDUPWIXl_rh5C_CLVjoaLcIpGDDrZlfUO20bX46N6ZJqKh3LUw=)
6. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGR5uRT_ENnNsIlg42ksklf2b4_srYyTF2YyzKibWotP4rfTj_deCVu1gZeigTSb8WApKj4NWpk1s1dR8vOSpIeb4iVHsos7ZZ-gmvYdrClJ55fSI6BgZrDcT3K3BD8k69-WrVETMg9Xw==)
7. [devclass.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEW2ad44tGw-CF73KatsszEJ7078UpPiWHGxojmXYcBV8SWYSU__ujtPtjJJ2ALJdTaSMGb_YLGiSSD-EshARnuHrVzJqMAEW-814O65-BQkddyEgcpImiDK09vmmgLLvFFnLotw6xVVgiKGI28-j-HnTTNFGTFSbAitYaJfPl5JF0x7R80vv-t5lTvWzW_sZvk6IlW_NhRj8Lngqb2Z_WWqInD7dA2-P4D4UwCs7qot-QbyJf-C1W8XIHTgxRLVSboczCO6BNzcXHmCjyv93AkYw==)
8. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF-1t-njwOApdO3EaOeiyH-k4_2qOEUOWcw9Iv69qGUvfZPOQZAC0ky2pO47GPiAjNNvH6fAs3mkJ2XeQpfC1iBR-y8lg6xbxSzhMZ_rifaPqNOyanZKDBh5lIS0z6eWpIRAT8VhcOurkiFF0RkgQwKJZ8pWfw=)
9. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFl-TqbOkeYEUKvWGiXtkYp8GPo3hyfHPaztiW11YxFI2moogGiiEqhS5teRnlYNIN-mwZuvR77xfMzBp834MYL_G3IqEBg_NrnjcqQuc71P8SiZLDBWfblm1QWxU0DvNHDyWbzwHmb-CSFldg-AJPYrsW0STm30JEqBiuOU2kUNyrczrZevIf9rJ0Z-H0J_p5_fjwdLJ1BC8-Toxtzun_jqqb_xo4KQfaBSYPVxAfhoJwSAp0tPoia99FUNroK0oJa7EvPX1o=)
10. [unity.cn](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFpIlA-QqSb_rv1-6y6acF-bxaAxq6s3iyoKy_6l0NgYqYceGv2beZ7o126ePU0RWrbw35O8sRWpje0W271ShnLWz8mbI32Sm4KioRMyLmnNJQlaE_vck72CuxiqYLJgOaT_Uguu1S9ew==)
11. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFQ4KgK9QBHLUZwKcytOqPPNW-ns31wXHGqgPJp0GJvV6RLArHuO4sqTtTlelZbNrLY83WsCGasF-UkAYBYz2qVf6MKvOL7uvLL-veMkwbDV4n8SJXNEemcu3ipA2J2ZVA=)
12. [jennapederson.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGzenn1PSGC7JJvX8InjxxWiMxEPpV2FVVMdrfRk0iPqf7k7uAnY_QCYrmbToJP5bXZ6dkgOmTErGTbILAlHAfmW35J264aCvCRlB2OOR4odBo26bM6-_r9wlhHL8ubAZOfvE321Z3pn6lDNS5OqNGb1odm_Vp7YEmP8hGPoqGlsMbnbllTmg==)
13. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHRa6NK7_zpBr5UCYi1tywAE94FDfcpDC4CTs6EMh5yXzDEbFxtXhii3tQhDKdrR6V5VOJA8U0Nyxex3ij-Ts1nnTzYybY76xPKuaJP82S3FqiLLtDjXe-EJmHLoWF9mVUlAnJyYlSSUWVHE-s=)
14. [nesbitt.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE5DVsMVt_NIg9I6lgIz1PMMeFEmZJU0z9ee36jzDzTIYZWugXMOjQ_LBHB_PjgRysMgAjoz3NEk_XP8NUhjR72KcTDt4rGfXNnlG-wlBKavwE_mRDUyneBdkgRfiSHsH588Xv7x0F_luZ10ZEZGlgNFfZqME-4WLm1yn14)
15. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHdNCT8GIEwNo8Gy9H8YxHSzNGUxaN8nNREs6yAvxWoVEkwK58q_Fh3ui1A4yu0_auwZaybJfi_dzeP7rUaFHVtSkf2qYLxNh5AhScZ4ai2tIbjiYCNwoEXVHe3CPUhPynRaZr_QWFSgtqgcYh5wdDg-byH)
16. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHFzEP-umrtL85bdf2dEAJd7pnNgTPSjyLuwFQEhsFnlCVDyiLb_OYDmi9gDuG4XKH3LGALguFH3e57qERLR0AG_J5DnJZ6DPnAw1V7LlJ3vNgh_XSv5EJUmn8TJnFEbRobxu4=)
17. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFmVKezAlD5yjjzOTY9fVxUzMt1mU7pWxnk1FtcJ4Zu2EnnTQKhH7-BoGsyQStX1KrJKUbcsyP9jKAJpjuhSzyzcQihWkvvh4cvZTnCJ2RVR5Nl4iHF23y7s9dYxuSkDMAZJyp7Y_5DDQk___8=)
18. [codeling.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEO_dhwtF1u5C2ZRyIlOHk2YXvFPIjWg0yKjXbIV0TiIw_xhZS546kgLhLNb4ov81C9OK725hnWTQ_SF9cOE1Ld77C1yK4lGuz6uCXXDotFSSl-XdLOAYnbgg==)
19. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGhHigA1f-0yDUNrS6tkte3pZJmxdMi9pThmNLn3yvyUMG6TYEWGbOcGbZPsBTADBxgFnrCkvXkHN9hNORa_iLKVI26ZTQAHRBeE9E2K_wwMp8MEK4ZfLed13zQRHP47ILGBAy8E7B5pR_QrPVh3g==)
20. [Link](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGzn7iYolEvwu621cLlOEIxpiuYA3X_Dp7uvSSf3twMsXQxBeF6xrrg6ed-LdjDc0ptYDKMN28w2mkNE5SmEpbd2eYMJ0F0vjvtp4GUCcgOkug5TG0y1Rh0Yez6_x_yrpKnfpY9kCy9tYRWVg2fyYpeZ4WORYsljJWzYNkC1TfkVQ==)
21. [geops.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGSoQaXYkmGm-YQGDT-nIaplR1oQ-3NneYR-yO1Bl0DRyYqtQe5G14id18tLq1p1qmyCekTzsvmxzxHqfgtkQMijrpP5CHzynBqB4Mxa5kCux3CTMpW7YWhNWmO7iphQ_a70RkZ5B5zuTk76jk=)
22. [joshthomas.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH-PsqSQrnK-8rcWJfEp_5NaT7zkkP5ANGyR6pmO9_zO4xXw8Lr44GJPNEypN11ST6P9lJ0o9DCMtvKJiHBZQnK9xB_uk5KVsLrT2wT4OV5OmVJzPWKXnHWUPSovYWTeQv7VlFSVLQURAkI1Bl9GNcX_5MmCF2_0tYQdIkwtMcGKxIarV70NucKi34SGUqZGisUupfhML7RTG17bqC9eFQowgwR-ov5kKQRIBcyeqgm3WtbUcomPw==)
23. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGnn-dDwoLLuSLiC-9fxIF1R5HfMYlcX8jmKLIWJ-SfgH3fMuz13xK3rg31Zc9DDnitCz35F-AO8bj9fHthSaFcI8yzTSHq0WSfCHCLykFdFSXp80A=)
24. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHOFW5fyhZoPhXsS92cknxsUrHRql0f5bnq515DmUFUGm9wZFM19VwRj3ak0zePLePOcLXlgdeLPsfJnJqjtH_pX_oqO_S98gYU6IqgkLWoGq0lwasu7rQr5wDKyfyAm0idkw==)
25. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFrSdQFKch4vuIZfMAqNzTQPsnuzT5o_EI6n1-eStcCRdlpo71m3r43ge864Q2WjvSXg3p6vIe_DAuHXR1uMyAAkZUTyjjLvbMcH8Fim9bOAQAnh5U5KvVVY3t9sMuv1XQV)
26. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFT66617GVSXhMnx82Y04i-D6ExyL-XZNfLDjq8XEaPI4SifyhVfDPAsZLqbCn3MPTXhjr2l3rzPWefnpy0LgolNV0OU4nJ8DZ9JyVZoKTeWrP09aGjjt3e3KxLjkwqBXM=)
27. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGRJfRyxYppKFWkGtgz8YYUTLe6z9m0t4aBYZyW65CtDFGSiIhxvEK8gNSJby4rsRQ7ooXIzQFKppnfONBKugKi51BX_T6gcvLJe8wWxSeLWIPPtzmYbETETpp-P8oVKyw=)
28. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF55fSTcBVdujQzRm7T7eetQ6B2Q7K5Ya4ztoXLvo6ov0PIe8ZGjb1uOR_muBLlTzZikHD89gw_tc8ZUgVLqEc1skIMQwJ4D7ChS_pL4cJEISdd4SRP7-Npv7ux)
29. [Link](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGVSP5aQ38WDv-wzfeLaPclbndv6u9TfTzmFdOZh591tDlEGC6XIR1C1wzwfbEvD07suZJyrfWMHJisVngMN-05vhnsvGmT7Hps8gcCOBKQnhMj-_-pXVYxlubuDGUpdiH6PqrF1zl4)
30. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHyxx4QoKNvtobBBPD6_fW1ovUjRrwaFCMJGUoBF6k_xE1E5nON_3YTIGl82SkF71jOaImopxXyNqauAW4OOaABTc5TCrcLHLhgilAsXwiuDEFFBOK-gPsPTeM7TMe3KFscc2pI7NsF8A==)
31. [deepnote.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEkMQ7azUGexa0RhM7J3yo_tmCnPspRJ201Lv7r6XZX94mBxCSDAFi1O2c_PQ9NdexFAfKwxHy_ktNp1mfF3xw6yLoIYNH-GNEXJvm3fau137I3_esez3yIWkqzrjYM68VtUEz-PH70HiZ_UpaxOnVQCG-uw4M=)
32. [astral.sh](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE91hRy1OJ4BfpBU1Yy1o5Rn0xJD1Gtb9WqW5ARnj0pUtdJhJspkUsd9NHCm6YSxXFrIHOVIBZBvfSavz-jtQBgIA8Les43xWoXRQy9L9YR6JNkGZID_v4spz5Uql5-U-TEqz1W_vih8w==)
