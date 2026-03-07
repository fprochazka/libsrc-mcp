# Comprehensive Technical Guide to Extracting Dependency Trees from Python Poetry Projects

### Executive Summary
The extraction of a complete, accurate dependency tree from Python Poetry projects requires a dual approach: leveraging the command-line interface (CLI) for immediate introspection and parsing configuration files (`pyproject.toml` and `poetry.lock`) for robust, machine-readable programmatic access. While `poetry show --tree` provides a visual representation of the dependency graph, it lacks a native JSON export option for the tree structure, necessitating alternative parsing strategies. For tool builders, the most reliable method involves directly parsing the `poetry.lock` TOML file, which acts as the single source of truth for resolved versions, hashes, and cross-platform environment markers.

With the release of Poetry 2.0, the landscape has shifted to support PEP 621 standards, allowing dependencies to be declared in a standardized `[project]` table alongside the legacy `[tool.poetry]` format. Successfully resolving source code repositories involves correlating locked package versions with metadata retrieved via the PyPI JSON API, specifically targeting the `project_urls` and `home_page` fields, while accounting for inconsistent version tagging conventions (e.g., `v1.0.0` vs. `1.0.0`) in Version Control Systems (VCS).

---

## 1. CLI Introspection: `poetry show`

The Poetry CLI provides commands to inspect the dependency graph. However, the output formats differ significantly in usability for programmatic tools.

### 1.1 The Dependency Tree Visualization
To view the dependency graph in a nested, visual format, Poetry provides the `--tree` option. This command outputs a text-based tree that shows the hierarchical relationship between packages.

**Command Invocation:**
```bash
poetry show --tree
```

**Output Format:**
The output uses ASCII characters to denote nesting. It lists the package name, the installed version, and the description, followed by its dependencies and their constraints [cite: 1, 2].

```text
requests-toolbelt 0.9.1 A utility belt for advanced users...
├── requests <3.0.0,>=2.0.1
│   ├── certifi >=2017.4.17
│   ├── chardet >=3.0.2,<4.0.0
│   ├── idna >=2.5,<3.0
│   └── urllib3 >=1.21.1,<1.26,!=1.25.0,!=1.25.1
└── tqdm *
```

### 1.2 Filtering Development Dependencies
Historically, the `--no-dev` flag was used to exclude development dependencies. In recent versions of Poetry (1.2+ and 2.0+), this flag is deprecated in favor of dependency groups.

**Deprecated Command:**
```bash
poetry show --tree --no-dev
```

**Current Best Practice (Poetry 1.2+ / 2.0):**
To exclude development dependencies or target specific groups, use the `--without` or `--only` flags [cite: 1, 3].

*   **Show only production dependencies:**
    ```bash
    poetry show --tree --only main
    ```
*   **Exclude specific groups:**
    ```bash
    poetry show --tree --without dev,test
    ```

### 1.3 Machine-Readable Output (JSON) Limitations
A critical limitation for tool builders is that **Poetry does not support combining `--tree` with `--format json`** [cite: 1, 4].

*   **Command:** `poetry show --format json` produces a flat list of installed packages with their metadata, but it loses the hierarchical tree structure (parent-child relationships are not explicitly nested in a single JSON object).
*   **Command:** `poetry show --tree --format json` results in an error or ignores the formatting flag, defaulting to text [cite: 1].

**Workarounds for Tool Builders:**
1.  **Text Parsing:** Write a parser for the indented ASCII output of `poetry show --tree`. This is fragile as the output format is not guaranteed to remain stable across versions [cite: 4].
2.  **Lock File Parsing:** The recommended approach is to parse `poetry.lock` directly. This file contains the complete resolution graph in a structured TOML format, which can be reconstructed into a tree programmatically.

---

## 2. Parsing `poetry.lock`: The Source of Truth

The `poetry.lock` file is a TOML-formatted file that contains the exact versions of all dependencies (direct and transitive) resolved by Poetry. It is the most reliable data source for building a dependency tool.

### 2.1 Top-Level Structure
The lock file consists of a list of `[[package]]` tables and metadata [cite: 5].

```toml
[[package]]
name = "flask"
version = "2.0.1"
description = "A simple framework for building complex web applications."
optional = false
python-versions = ">=3.6"
files = [...]

[package.dependencies]
click = ">=7.1.2"
itsdangerous = ">=2.0"
```

### 2.2 Available Fields per Package
Each `[[package]]` entry generally contains the following fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | String | Normalized package name (e.g., "flask"). |
| `version` | String | Exact locked version (e.g., "2.0.1"). |
| `description` | String | Brief summary of the package. |
| `category` | String | "main" or "dev" (Note: In newer versions using groups, this may be less relevant, but it persists for backward compatibility). |
| `optional` | Boolean | `true` if the package is part of an optional group or extra. |
| `python-versions` | String | Python version constraints required by this package (e.g., `>=3.6`). |
| `files` | Array | List of dictionaries containing `file` (filename) and `hash` (sha256) [cite: 6]. |
| `source` | Table | (Optional) Details if the package is from a non-PyPI source (git, url, private repo) [cite: 7, 8]. |

### 2.3 Dependency Definitions within Lock File
Dependencies are listed under `[package.dependencies]`. These keys map to version constraints.

```toml
[package.dependencies]
requests = ">=2.25.0"
urllib3 = {version = ">=1.26", optional = true, markers = "sys_platform == 'win32'"}
```

*   **Simple Constraint:** A string representing the version range.
*   **Complex Constraint:** An inline table containing `version`, `markers` (environment constraints), and `optional` flags [cite: 9, 10].

### 2.4 Parsing Strategy
To reconstruct the tree:
1.  Load `poetry.lock` using a standard TOML parser (e.g., `tomllib` in Python 3.11+).
2.  Create a map/dictionary of all `[[package]]` entries keyed by `name`.
3.  Load `pyproject.toml` to identify the **root** dependencies (direct dependencies).
4.  Recursively traverse the `[package.dependencies]` of the root items, looking up children in the package map created in step 2.

---

## 3. Parsing `pyproject.toml`: Dependency Declarations

The `pyproject.toml` file defines the direct constraints. Poetry 2.0 introduced significant changes by adopting PEP 621, allowing two different ways to declare dependencies.

### 3.1 Legacy Format (`tool.poetry`)
Prior to version 2.0, and still supported for backward compatibility, dependencies were defined in `[tool.poetry.dependencies]`.

```toml
[tool.poetry.dependencies]
python = "^3.9"
requests = "^2.28.1"
gunicorn = {version = "^20.1", optional = true}
```

### 3.2 PEP 621 Standard (`project`)
Poetry 2.0+ supports the standard `[project]` table [cite: 11]. Tool builders must parse **both** sections to ensure compatibility.

```toml
[project]
name = "my-project"
dependencies = [
    "requests>=2.28.1",
    "flask==2.0.1"
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]
```

**Key Differences:**
*   **Syntax:** `tool.poetry` uses TOML key-value pairs (Map). `project.dependencies` uses a list of PEP 508 strings (Array) [cite: 12, 13].
*   **Enrichment:** Poetry 2.0 allows using `[tool.poetry.dependencies]` to "enrich" PEP 621 dependencies with Poetry-specific metadata (like `source` or `develop = true`) [cite: 12].

### 3.3 Version Constraint Syntax
Poetry uses a specific syntax for version constraints that tools must interpret correctly [cite: 9, 14, 15].

| Symbol | Name | Meaning | Example | Range |
| :--- | :--- | :--- | :--- | :--- |
| `^` | Caret | SemVer compatible updates (locks left-most non-zero digit). | `^1.2.3` | `>=1.2.3 <2.0.0` |
| `~` | Tilde | Minimal version with minor updates allowed (locks major and minor). | `~1.2.3` | `>=1.2.3 <1.3.0` |
| `==` | Exact | Exact version match. | `==1.2.3` | `1.2.3` |
| `*` | Wildcard | Any version. | `*` | `>=0.0.0` |
| `>=` | Inequality | Manual range specification. | `>=1.2` | `>=1.2.0` |

### 3.4 Dependency Groups
Poetry organizes dependencies into groups.
*   **Implicit Main:** Dependencies in `[tool.poetry.dependencies]` or `[project.dependencies]`.
*   **Standard Groups:** `[tool.poetry.group.<name>.dependencies]`. Common names include `dev`, `test`, `docs` [cite: 16, 17].

Parsing logic must iterate through all defined groups to gather the full set of direct dependencies.

---

## 4. Cross-Platform Resolution & Markers

One of Poetry's strengths is creating a "universal lock" that works across platforms.

### 4.1 Marker Logic in `poetry.lock`
Poetry resolves dependencies for *all* valid environments and stores them in the lock file. Platform-specific dependencies are annotated with environment markers [cite: 9, 18, 19].

**Example:**
```toml
[[package]]
name = "colorama"
version = "0.4.4"
description = "Cross-platform colored terminal text."
optional = false
python-versions = ">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*"
files = [...]

[package.dependencies]
pywin32 = {version = ">=1.0", markers = "sys_platform == 'win32'"}
```

### 4.2 Handling Markers Programmatically
When building a dependency resolution tool:
1.  **Read the `markers` field** in the dependency declaration within `poetry.lock`.
2.  **Evaluate the marker** against the target environment (e.g., using `packaging.markers` from the standard Python packaging library) if you are resolving for a *specific* machine.
3.  If resolving for a "universal" tree, include the dependency but annotate it with the marker condition [cite: 9, 10].

Poetry 2.0+ explicitly includes resolving markers and groups in the lock file to optimize installation without re-resolving [cite: 11].

---

## 5. Finding Source Code Repositories

Poetry projects often depend on packages hosted on PyPI. To find the source code (e.g., GitHub, GitLab), you must bridge the gap between the package name and its metadata.

### 5.1 PyPI JSON API
The most reliable method is to query the PyPI JSON API.

**API Endpoint:**
```
GET https://pypi.org/pypi/{package_name}/{version}/json
```
*   Omit `/{version}` to get the latest version.

### 5.2 Extracting Source URLs
The JSON response contains an `info` dictionary. You must check multiple fields as there is no single standard field for the source repo [cite: 20, 21, 22].

**Priority of Fields to Check:**
1.  **`info.project_urls`**: This is a dictionary of arbitrary keys. Look for keys (case-insensitive) such as:
    *   `Source`
    *   `Source Code`
    *   `Repository`
    *   `GitHub`
    *   `Code`
2.  **`info.home_page`**: Often points to the repository if `project_urls` is missing.

**Example JSON Snippet:**
```json
{
  "info": {
    "project_urls": {
      "Homepage": "https://example.com",
      "Source": "https://github.com/username/repo",
      "Tracker": "https://github.com/username/repo/issues"
    },
    "home_page": "https://github.com/username/repo"
  }
}
```

### 5.3 Version Tagging Conventions
Once the repository URL is found, linking to the specific version requires guessing the tag format. There is no enforced standard, but conventions exist [cite: 23, 24].

**Common Tag Patterns:**
1.  `v{version}` (e.g., `v1.2.3`) - Most common.
2.  `{version}` (e.g., `1.2.3`).
3.  `release-{version}` (Rare).

**Strategy:**
When constructing a URL to the source code tree (e.g., `https://github.com/user/repo/tree/{tag}`), try the `v` prefix first, then the bare version number.

---

## 6. Private and Custom Repositories

Poetry allows configuring private package sources. This affects how a tool resolves the artifact location.

### 6.1 Configuration in `pyproject.toml`
Private sources are defined using `[[tool.poetry.source]]` [cite: 25, 26, 27].

```toml
[[tool.poetry.source]]
name = "private-repo"
url = "https://pypi.example.com/simple"
priority = "supplemental"  # or "primary", "explicit"
```

### 6.2 Lock File Representation
In `poetry.lock`, packages from private sources include a `source` block [cite: 7, 8].

```toml
[[package]]
name = "private-lib"
version = "0.1.0"
[package.source]
type = "legacy"
url = "https://pypi.example.com/simple"
reference = "..."
```

**Handling Strategy:**
If a tool encounters a `source` block in the lock file, it should **not** query public PyPI. Instead, it must respect the `url` provided in the lock file. Note that accessing metadata from these private endpoints usually requires authentication (HTTP Basic Auth or tokens), which Poetry manages via `auth.toml` or environment variables [cite: 26, 28].

---

## 7. Poetry Export Plugin

For tools that prefer parsing `requirements.txt` over TOML, Poetry offers an export functionality. In Poetry 1.x, this was a core command. In Poetry 2.0, it is a separate plugin [cite: 29].

### 7.1 Installation (Poetry 2.0)
```bash
poetry self add poetry-plugin-export
```

### 7.2 Generating Requirements
This command resolves the lock file and outputs a standard `requirements.txt`.

```bash
poetry export -f requirements.txt --output requirements.txt
```

**Useful Options:**
*   `--without-hashes`: Removes hash verification (easier to parse).
*   `--with dev`: Includes development dependencies.
*   `--without dev`: Excludes development dependencies (default in some versions).
*   `--only groupname`: Exports specific groups [cite: 29].

This artifact is useful if the analysis tool already supports `requirements.txt` parsing but lacks TOML support.

---

## Summary of Parsing Strategy for Tool Builders

To build a robust tool that resolves dependencies and finds source code:

1.  **Check for `poetry.lock`**: If present, parse it using a TOML library.
2.  **Build the Graph**: Map `[[package]]` entries by name. Use `[package.dependencies]` to build edges.
3.  **Identify Roots**: Parse `pyproject.toml`.
    *   If `[project.dependencies]` exists (PEP 621), use those as roots.
    *   If `[tool.poetry.dependencies]` exists, use those.
    *   Collect groups from `[tool.poetry.group.*]`.
4.  **Enrich Metadata**: For each package in the graph:
    *   Check if it has a `source` field in `poetry.lock`.
    *   If `source` is missing (implies PyPI), query `https://pypi.org/pypi/{name}/{version}/json`.
    *   Extract `project_urls` to find the Source/Repository URL.
5.  **Resolve Tags**: Attempt to locate the specific git tag using `v{version}` or `{version}` against the discovered repository URL.

**Sources:**
1. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFI1Si8GGg3xAj2iBw5_ejTMkQm-z8-Is_vWlqiyXiF9H37p8r67C5rxWBOL9ZuvyX_DWckK2674BzUQMOdM1xLw_vf9r4ar57eAvUNpJgy5c5GO61Ss1qwAQ==)
2. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQElUQtUNUqLHbUaR8PiFJw6lmgsf3hCdJH2DP9kK-QNhiQZrwlc2paXKJCvUHTys7_uws0TSCvdKLovfU1NY6j7VPkNOof6TShrwgpLO-6KoA==)
3. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF-e0UiW24DgnxfgSkTj_NSwohGvX37zwLVy7--77U_qfLasNBI48cdXQ190gsCJ8MX2XQ0M_eOKNXD8x4F_Wu0DY9XIq0KxOq50nfQou5ziVGr7YQjg77tb09cIF8=)
4. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEBx9JucJi_NOCmus3TCkwtEO8R2PtSSokg_M6B4trHk9T3BmFmCpwjrH2Bvj8UKHsP_SCICm6KRqPnHgJd2_KRD5Utaobg9fTFu__OUN42MqQ1nQ5nwgvERDVdVcCkguT-8DbVrR25WNKU5K4=)
5. [geeksforgeeks.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHw8Kho5vmqB_yNolxKmGdK39Gq81kNduVQT75ONdARiZ7EsPrk8y5cGYLVZiYpwZCHfQ-b6jw6Y3_vWchbltQ2pQ-IBV6UxN6o67Skyh6fgfiA78-VA_uVetpZtPgJkPn-AEdj0s4V3GQbtf3LzR0uzulFFvnyFYv2vFhgu96FsxQZSoGLf2rbs7SkR6n46zz8)
6. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG94EYnoVGBra8E1wXLkNGc-3BwJ2mGTqCAqpL-F3Ni434jqfzV8Amu6iUlWcY5qWcPZkSv-UIfMhdOKVttvrjPh7feu0Hn12aiaR6CMo5r7fXCFMaSB1V0x5iL9IemhU-yt0P-gjU8fHNkCC7jLxhAr3syeGHXKIZ1eCZHCY0vgvV5ilHtrisRJgC6SstDqy23CucQ)
7. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH7AhTPHpAahHJywF_PjGnmeFe9iH2Hanp99azMzH2_FCyB80970T_8OFEnHLuG4pcbUZYS2qO-7aXKNhqY_-Cf42bRCtLUlCYg0N9ATnT76Qo4YePHS_pbNyW8OH__9W-DTIEkynK2ZAQ=)
8. [thedatarefinery.co.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHBDqDDWuK2IW64Nj7AOWJb-KvTTH5NFYYhRfqziu39ZPyNg-mNTeG-IB-CQSRuR1HQ8abdWjjbcKhdn9WdBt-fWWZJ-Bznlpi982tDgzQ4yxbntH7DAUV7at9jMnYYB0ZOj5_tKdfGQDI7seAxgCKHbJ6PRtGmGYCvYjGP5Cse9w==)
9. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHCXpRQk6KLQaF-KUcFJq6wO8StHsD5OmXJW8vd-JpEy51yGxs5QB4nrMcwHkRgEgkULrIFQ9Y_YxmQ73_8SduB4KGTa6DUrPSIYfmALIMnJ0E_Gissk6XQl4-V9DuKmgL57bUZe3WrqqMzAAatKw==)
10. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEK7VVrrjucED1rh903cCPie6FsUCdxXvBa-xgxOQwpQw2ePTNt_Oq9IDlN2TBRIWMEn5xigGel4znNmTLbmuwEJv4jR54pMaMSIpu2hYmEy-XgpybOyxW17b-_WM_uYNP0elbTXy0NOyCw)
11. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEo1XouPbSoYELm_gEN8MLtPtVeO0rhKS5mtfPFqtHia2E0Da6io_2lUdaTMcPwfPz2BSLKW9AXELQWkkdp1SWec7WbYCQFUOJYmhpCToSiKeLsEwOx9iOz_4L-7UBzNJQKpKjbeQONdr4enewl)
12. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF2OzRYWz_Zc1V4a1cX7Ko2hcX_v1W4wy3McvINiQrMSxCBh_UG4wRO1OeSTLUsfN6xWTVoyM-heL_2EiWGk9ADvpgoZBl5ZnLhNc8RobxHjDRzLlL4mgOiOpEiBj_lp-pJQ3mWZWoHVx8ecA==)
13. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGV4r7JHNQ68BEXslBnlUDP4KrXk7iwMGsFRmotRXiCpBcnr-CYpWpjCNO10Xhe5wSmw2iJhsZMxJpG6Xs-iABzIfMh4mxLwzRWPzDSzu9fdGtzteVjdjk=)
14. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEeoRA3XAt4RZWS15LGTTyAMMHIzDEpTie9fE5zGNNGkZQJknPHOPxjmjKw3Bi9EqgvakjOa-CG38AvVZ-WLM3RZsuYMGwpwbEI_tCdzOJUIKbdXlNnlo7zjVKELzap9cyQFPb7NG1VnK-Ew3Fmq-K0sWDu2Vx-GmvgvH3ceij-bzTVqQWdTlgDbVrfo1IJ)
15. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEnohzD9LzHcoPgRicQ6E1QIPfyACzSm7m0ILBhSaoMUu0oUeBAIHqk1LAgExvUcY9l8TGdufQW_j6m4CdyZjM4w2zBxHfiHZxzp-gkbRi6W73ah-WnI0OLe1cVZmi5_aLj6ARqLhqBSaZ-imH9KpOhMHM=)
16. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFVG57kkFOUW_yh8O1OVZnq3NRvYWanRIOnU-LGwj4wBsFjiJC-BuupLNITGK8mNeCNUcfa8wXoOo4AH45vSV30d-PXIX2rzm8nije-Wj1n9dx7vdAEB8WogJGO1cWHHIaVMHPRi9we)
17. [oneuptime.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHousRK8JwXhNbyIO9bLyX9V7Cm27xy2_Kol4cW506D7s4Ju3CO7USARpj8zTIDpOOkN_oPROrnkpPtNff3hDoN-3kVju5dLrpFAKn_2zaaFUQ_umGNVDiPWKulkMseN_AsmXBWVEWVwXbDqohs0BI0HWhEySpxMWE7qHcFxlAMaab1Jyc5napTyA==)
18. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEhElib0iZGXM_sGxqAYyq2zmsyYdE3b20xhklw1qfjcf0z0DeWKZNANfxBGF-a2T5ZgZXsXhTab8L16wI_X2HYeUMR20PgPVQu8kNw5A1E0rsWIbCCeRWyiYKY1vqCQWIXLExSgtGdF0u4vcYw8nzkQhM0a3sgNV5p-ex7usr3JWV_eEep1JsuGhSohis=)
19. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFUOWdyflt301Ph7KAyhjzvmZlJliLEVSFTnTeDVHk9WzpA9rdIIemWyS2zQEuOF2oXOY7Gda-4_bqLoKbhCJA5aOTRPcEj5iGs8kxkoWuApeBdEnsAWAUB64KJ2j81ErnB2_y6HSQ3KDDpTuHm_n9OI10WqEcUOcSvTf8WPk9PgvQsxDOw8Iv35kuW)
20. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFjFPHBlCtHMNHNFjuj7JSt0jKMvOM0mzaXLFbd66d0C54QJYLX80UxwljFq-1rgHGax3Ed9TN5cJRCXhjmoJhI5Vz-GiYHq7O9JWODU5g2z3reGLnH)
21. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEcj55JiM2Xn--8BmkGzqCYT3q2OX70H79mblkkSTjiXxfFocLf6YikUumvdbjb021ReXUDFFDHh-CnlkNRNWr_ZeULWrXAMgnIwapi4rq6AX6q1g3hgLoHPoRSiqz3ToD4dnw=)
22. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFrfNk3bprmPN2mGneKbJL22lbZHevMbn9W2LoeAvY-zK8WNvnvjFYwqdxyAC0PnghASGd-nzhIARfqmsPwpoLitkwFDWvK7T_Pm-AUbARNDcnm3KiVLj9W-p1lS3g=)
23. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHF2cBO3QDzA0pHyWRz65lx7RG--pfFcYHxmpXZ1UEgrgud5B0zZD0nooiNNIJtBUTMPtLAnV6TkxAVSDW_P9nJTGcFIJdtXDhTwQlZtGitJ9qBHFn2MqQ6KR_OEYQmkcDF2w8Oylmxg3C-BqOK)
24. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGYRt0sizhFdEQJgnmyGPUfREPKYSObkA1XrnphcK-dd86fI5-3U5cq047yxoFpduCJywJJ-skxmtzhMAyrwG9QEJ7qybFl8MqShALRzXxgCGIYluz6kYPLbNviLgSFX9YmdnmIyxnPU0pJvawUTNdvY6plHhWAbcCTO0g8fXwfaRNBBcy_AA8YeXsTefTM1pRuN0w0XsloQsjykgMnYQvmlg==)
25. [python-poetry.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEVbW6mAnst_WS31v31RkOj4py9VrouHbagyhoBjZI81j_cuKFeM9HAVPQNTNHEk20hXqQBkEwUycMsi6oadnsoJB2bx3SC48iewSgyZ3MAsZPUwdjszs1R3yUoHmL3HV3fLw==)
26. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHb6cs1u_09fTsiK9wOAbj4v4R64jOsb0sRlnzihSf299qiYihsNGQVs5kKOTTbBuyaqE2Vt954bxaiMI7rAnvew4SmMTGnc58H8YIi0y1H1gNZD0Sn7oRKoA21FCkxe6QLWF7EscS5Qus=)
27. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGwctslSV8DIuNcASOTzTcCllkW0V-mo1uCSKTuNOZN6DBgr1KrrQQ95ap1f0FYVAAda1FfE3VRAkj6nvigfa3F73jq7D6V_kZmOBAZHex2IAhXnL0zyNtkf3jc5OER6val0huXxK_nF-A=)
28. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFd_lqd8g0_KBI0toqZyLXETBd-7CVu6YY8tyTGODd9Dhowl8gKqeCKBuK1CC7BrWF0vcdV13Ufq-1KFYQdiPRd0YHB5iM2Y0seb3KDmPsE1QCmI1mMf9Stk5txJb36prqHp6hGjDGzXryd5Equ14gSc5ZPi93M32DxrXDghUlIfzZgei8qQNc2iZdWRMISOj8jsA==)
29. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGZDcdUhumgYLiugcTVGp9tREz-Em11kV2jcQbq3OgquQuO9cODj9v-akXF8Ca-Jg_ovgg7ob-b3QPIduVr8neOWzStfjQNsDUIKOe52I7amUiYsVrrIzTqRufJ_t9FqrepCiggTlcGn1mgKg==)
