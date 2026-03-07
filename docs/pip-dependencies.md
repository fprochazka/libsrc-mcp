# Comprehensive Guide to Programmatically Extracting Python Dependencies

## Leading Paragraph
The extraction of dependency information from Python projects is a multifaceted challenge due to the ecosystem's evolution from imperative configuration scripts (legacy `setup.py`) to declarative metadata standards (`pyproject.toml` and modern `pip`). Programmatic extraction methods generally fall into three categories: **environment inspection** (analyzing installed packages), **static analysis** (parsing source files without execution), and **remote metadata retrieval** (querying the Python Package Index).

Key strategies involve leveraging the `pip` command-line interface's JSON output capabilities for installed packages, utilizing the `pipdeptree` utility to resolve dependency hierarchies, and parsing `requirements.txt` files using the `packaging` library to handle complex version specifiers. For uninstalled projects, `setup.py` presents significant security and parsing challenges, often necessitating Abstract Syntax Tree (AST) analysis to avoid arbitrary code execution. Furthermore, while the PyPI JSON API provides accessible metadata including source repository URLs, this data is self-reported and unverified, requiring cautious validation for security-critical applications.

---

## 1. Environment Inspection: The Pip Command-Line Interface

The primary method for extracting dependencies from an active environment is the `pip` command-line tool. While originally designed for human interaction, recent versions have introduced structured output formats suitable for programmatic consumption.

### 1.1 `pip list --format=json`
The most robust native method for retrieving a flat list of installed packages is `pip list` with the JSON format flag. Unlike `pip freeze`, which is designed to produce a reproducible environment file, `pip list` reports the current state of the environment with metadata [cite: 1].

**Command:**
```bash
python -m pip list --format=json
```

**Output Structure:**
The output is a JSON array of objects, where each object represents an installed distribution.
```json
[
  {"name": "requests", "version": "2.28.1"},
  {"name": "numpy", "version": "1.23.5"}
]
```
For packages installed in **editable mode** (development mode), the JSON output includes an `editable_project_location` field, indicating the local directory of the source code [cite: 1]. This is critical for tools that need to distinguish between library dependencies and the project currently under development.

### 1.2 `pip freeze` and Output parsing
`pip freeze` outputs packages in a format compatible with `requirements.txt`. It is less suitable for direct programmatic parsing than `pip list --format=json` because it produces unstructured text lines and may include direct URL references or VCS (Version Control System) links rather than simple name-version pairs [cite: 2, 3].

**Characteristics:**
*   **Format:** `<package_name>==<version>`
*   **Exclusions:** By default, it excludes build tools like `pip`, `wheel`, and `setuptools`, whereas `pip list` includes them [cite: 2].
*   **Use Case:** Its primary programmatic use is to generate a snapshot of the environment for replication, not for metadata analysis [cite: 4].

### 1.3 `pip show` and Metadata Extraction
The `pip show` command provides detailed metadata for a specific package, including its "Location" (installation path), "Requires" (dependencies), and "Required-by" (dependents) [cite: 5].

**Parsing Challenges:**
`pip show` outputs data in an RFC 822-like format (Key: Value) but does not officially support JSON output as of early 2024 [cite: 6]. Although proposals for a `--json` flag exist, they have largely been superseded by the `pip inspect` command [cite: 6].

**Programmatic Approach:**
To extract dependencies via `pip show`, one must parse the text output. The `Requires` field is comma-separated.
```python
import subprocess

def get_dependencies(package_name):
    result = subprocess.run(
        ["pip", "show", package_name], 
        capture_output=True, 
        text=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Requires:"):
            # Remove "Requires: " prefix and split by comma
            return [pkg.strip() for pkg in line.split(":", 1)[cite: 7].split(",") if pkg.strip()]
    return []
```

### 1.4 The `pip inspect` Command
Introduced in `pip` v22.2, `pip inspect` is the modern, officially supported method for obtaining a complete, structured report of the Python environment [cite: 8]. It produces a detailed JSON report containing installed distributions, their metadata location, and requested state.

**Output Structure:**
The output follows a strict schema versioned for stability. It includes a `requires_dist` field within the metadata, which lists dependencies with their environment markers (e.g., `extra == 'dev'`) [cite: 8]. This is superior to `pip show` as it provides the raw metadata necessary for accurate dependency resolution.

---

## 2. Parsing `requirements.txt`

A `requirements.txt` file is not a standard configuration file but a list of arguments passed to `pip install`. Consequently, parsing it requires handling complex logic, including version specifiers, local file paths, and options like `-r` (recursive inclusion) and `-e` (editable installs).

### 2.1 Standard Libraries vs. Specialized Parsers
Standard libraries like `pkg_resources` (deprecated) or `packaging` can parse individual requirement strings (e.g., `requests>=2.0`), but they cannot parse the file structure itself (e.g., lines starting with `-r` or `--extra-index-url`) [cite: 9, 10].

**Recommended Tool:** `pip-requirements-parser`
This library is a standalone fork of pip's internal parsing logic. It allows for offline parsing of requirements files and correctly handles pip-specific options that standard regex approaches miss [cite: 11, 12].

### 2.2 Specifiers, Markers, and Constraints

**Version Specifiers:**
The `packaging.requirements` module (a dependency of `pip-requirements-parser`) implements PEP 440 and PEP 508 standards. It parses strings to extract:
*   **Specifiers:** `==`, `>=`, `~=` (compatible release), `!=`.
*   **Extras:** Optional dependency sets, e.g., `requests[security]`.
*   **Environment Markers:** Conditions for installation, e.g., `; python_version < "3.8"` [cite: 10, 13].

**Code Example (Using `packaging`):**
```python
from packaging.requirements import Requirement

req_string = 'requests[security]>=2.8.1; python_version < "2.7"'
req = Requirement(req_string)

print(f"Name: {req.name}")           # requests
print(f"Extras: {req.extras}")       # {'security'}
print(f"Specifier: {req.specifier}") # >=2.8.1
print(f"Marker: {req.marker}")       # python_version < "2.7"
```

### 2.3 Handling File-Level Options
A robust parser must handle:
1.  **Recursive Includes (`-r`):** A line ` -r base.txt` instructs pip to process another file. A programmatic parser must recursively open and parse these files [cite: 14, 15].
2.  **Constraints (`-c`):** Files included via `-c` restrict versions but do not trigger installation. These must be tracked separately from requirements [cite: 16].
3.  **Editable Installs (`-e`):** These lines usually point to a file path or VCS URL (e.g., `-e git+https://github.com/user/repo.git#egg=pkg`). They often lack a clear name-version structure until the setup information is read from the target [cite: 17, 18, 19].

---

## 3. Dependency Trees with `pipdeptree`

Standard `pip` commands produce flat lists. To understand the relationship between packages (i.e., which package requires which), the tool `pipdeptree` is essential. It visualizes the dependency graph and identifies conflicting dependencies [cite: 20, 21].

### 3.1 JSON Output Formats
`pipdeptree` offers two JSON modes valuable for programmatic use:

1.  **Flat JSON (`--json`):**
    Returns a list of all packages, where each package object contains a `dependencies` list listing its immediate requirements. This is useful for mapping direct relationships [cite: 21, 22].

2.  **Nested JSON (`--json-tree`):**
    Returns a nested structure representing the tree. Top-level packages are roots, and dependencies are nested children. This format perfectly represents the hierarchy but may duplicate data if multiple packages depend on the same library [cite: 21, 22].

**Command:**
```bash
pipdeptree --json-tree
```

### 3.2 Conflict Detection
`pipdeptree` is also used to validate the environment. It checks if installed versions satisfy the requirements of dependent packages.
*   **Example Output Key:** The JSON output includes `required_version` (what the parent wants) and `installed_version` (what is actually present).
*   **Validation:** If `installed_version` violates `required_version`, `pipdeptree` can be configured to warn or fail, aiding in automated environment health checks [cite: 20, 21].

---

## 4. The PyPI JSON API

For extracting metadata about packages *without* installing them, the Python Package Index (PyPI) provides a JSON API. This is the standard way to inspect upstream availability, metadata, and release history.

### 4.1 Endpoint Structure
The metadata for a specific package version is accessed via:
`https://pypi.org/pypi/<package_name>/<version>/json`

For the latest version:
`https://pypi.org/pypi/<package_name>/json` [cite: 23].

### 4.2 Critical Data Fields
Upon querying this endpoint, the response contains an `info` dictionary with key metadata:
*   **`requires_dist`:** A list of strings defining the package dependencies (following PEP 508 format). This allows you to resolve the dependency tree of a package remotely [cite: 8, 24].
*   **`project_urls`:** A dictionary of URLs provided by the maintainer, typically keys like "Source", "Homepage", "Documentation", or "Tracker" [cite: 25, 26].
*   **`releases`:** A dictionary mapping version numbers to lists of artifacts (wheels, tarballs), including checksums (MD5, SHA256) [cite: 23].

**Note on Stability:** The `releases` key within the version-specific endpoint (e.g., `/pypi/pkg/1.0.0/json`) was deprecated/removed in some contexts to improve performance, but remains available in the project-level endpoint [cite: 23].

---

## 5. Reliability of PyPI Metadata for Source Discovery

A common programmatic task is linking a PyPI package to its source code repository (e.g., GitHub or GitLab) to perform code analysis. This relies heavily on the `project_urls` field in the PyPI JSON API.

### 5.1 Self-Reported Nature
The `project_urls` metadata is entirely self-reported by the package author in `pyproject.toml` or `setup.py`. PyPI does not verify that the "Source" URL actually corresponds to the code in the uploaded artifacts [cite: 25, 27].

### 5.2 The "Phantom Files" and Malware Risk
*   **Discrepancy:** It is possible for a package to point to a legitimate repository (like `requests/requests`) while containing malicious code in the distribution (`.whl` or `.tar.gz`). This vector has been used in software supply chain attacks [cite: 28].
*   **Availability:** Research indicates that tools can only retrieve correct repository information for approximately 70-72% of PyPI releases using metadata alone [cite: 29].
*   **Verification:** To ensure reliability, one must verify the link. This can be done by downloading the source distribution (`sdist`), extracting the revision hash (if available), and comparing it against the repository tags, though this process is complex and resource-intensive [cite: 29].

**Conclusion:** `project_urls` should be treated as a hint, not a verified link. For security contexts, the actual artifact downloaded from PyPI must be analyzed.

---

## 6. Extracting `install_requires` from `setup.py` and `setup.cfg`

Legacy projects (and some modern ones) use `setuptools` for configuration. Extracting dependencies from these files without installing the package is complex.

### 6.1 `setup.py`: The Dynamic Execution Problem
`setup.py` is a Python script. It can execute arbitrary code, calculate dependencies dynamically, or import modules that are not yet installed [cite: 7, 30].
*   **Method 1: Execution (High Risk/Accuracy):** Running `python setup.py egg_info` generates dependency metadata in an `.egg-info` directory. This is accurate but executes the script, posing security risks and requiring the build environment to be present [cite: 31].
*   **Method 2: AST Parsing (Low Risk/Lower Accuracy):** Using Python's `ast` (Abstract Syntax Tree) module to parse the file text. This avoids execution but fails if `install_requires` is generated dynamically (e.g., read from a file or calculated based on OS) [cite: 7].

**AST Extraction Example:**
```python
import ast

def parse_setup_ast(setup_file_path):
    with open(setup_file_path, "r") as f:
        tree = ast.parse(f.read())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup":
            for keyword in node.keywords:
                if keyword.arg == "install_requires":
                    return ast.literal_eval(keyword.value)
    return []
```

### 6.2 `setup.cfg`: Declarative Extraction
`setup.cfg` is a static INI configuration file. It is much safer and easier to parse using Python's built-in `configparser`. The dependencies are usually found under `[options]` in the `install_requires` key [cite: 32, 33].

**Parsing `setup.cfg`:**
```python
import configparser

config = configparser.ConfigParser()
config.read('setup.cfg')
if 'options' in config and 'install_requires' in config['options']:
    deps = config['options']['install_requires']
    print(deps.splitlines())
```

---

## 7. Virtual Environment Detection and Targeting

Programmatic tools must determine if they are running inside a virtual environment (venv) and potentially extract dependencies from a *different* venv than the one running the tool.

### 7.1 Detection (`sys.prefix` vs `sys.base_prefix`)
The most reliable way to detect if a Python script is running inside a virtual environment is checking if `sys.prefix` (current environment path) differs from `sys.base_prefix` (base system Python path) [cite: 34, 35].

```python
import sys

def is_venv():
    # sys.base_prefix is available in Python 3.3+
    return (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
```
Legacy checks for the `VIRTUAL_ENV` environment variable are less reliable as they depend on the activation script, not the interpreter state [cite: 34].

### 7.2 Targeting a Specific Venv
To inspect a virtual environment other than the current one, one should not activate it via shell scripts programmatically (which is fragile). Instead, invoke the pip executable located inside that venv's `bin` (Unix) or `Scripts` (Windows) directory [cite: 36].

**Technique:**
1.  Locate the python executable: `/path/to/venv/bin/python`
2.  Run pip via subprocess:
```python
import subprocess
import json

venv_python = "/path/to/target_venv/bin/python"
result = subprocess.run(
    [venv_python, "-m", "pip", "list", "--format=json"],
    capture_output=True,
    text=True
)
deps = json.loads(result.stdout)
```
This ensures the `pip` command inspects the libraries installed in `target_venv` regardless of the host environment [cite: 37].

**Sources:**
1. [pypa.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEFwxu1sKG60OM2W7Zse2Pf2OqX6EMDMmVZYCKRt7d48Um07KejcrK9ibCPXiJg6a9xx69YAb5LvXAAFQF0WizlV3i3Ecr-pXUPyGpPERosbE647SYv9Hekb9_FhNhmR2MT)
2. [nkmk.me](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFJRd3av9QVYTylGJSVBmivcpZ9IxLJKu8gJXWl0oj4Ikp92SYIr_klivvyCltGxfn0SXgd61rExVni6uLwTWN3Hrg6TBw6F6H6QgkSLWgzVtA45-8JFOhm21RQ0V1q87pvqnEt_A==)
3. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG2_P1ZrdcpRy4MIn7UztaYIJORbKYQ7hn_F3iWq7bFWfG3PA3wloiAlZmZoicfNOP7zEZD_f474loVJLT9BndN38DbfSBrUhgDJ46RmXLVUftj8zDba7Z54uq1Lli2_n0fXUzCdRqfo5XtfDNuIpn9WfvgWk6J15Pf)
4. [youtube.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFl7fW7n23Bnm7j04Mzy4QKVMUrCOqnLRXSNt0RmKrLfVgHJ6kYBEM5lbCeQQqL3ri71l2I2pExt93Mo16M_8rxStxy1h3S6dw_LVFdYvFNnrC3VgbmdPS3DyeE-XWxhTGC)
5. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGCFn-lzDZuZlFG2raB7fIrIoPI6sP3KOEiSExkDFVrWWIv_KXfOPGRpUDBm7Q-fIyHhy9uV7R-6M0C9h_V7t5tTGX3-gw2qhVWRoDdlAJ0RJ9kEZaNSmbggCv2cbmLdcNK-yVUfEhRnFl207VUZfiT0rooZrzUSfszoc0GQPcO2Jwg2sIzFuSsjkWO6aoYyCC95PlSD4BCpLWzVxg_EyKVDt-zhLNviHZ7iyNfmmcx7W3g)
6. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQETemU4oXzWRHJ-Hs8_aIaDJHCdxs2GMUVzwtUzHyEjmeMxK6AFiFN6ccIHERgVu616VGN51ezn6e6b_Y8c_CwTa_l4txYeFtW51ag32-05lA8J8N9TQurFfIt6jFc=)
7. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH2Ay6jOwp1nq8B2RUqBpFMTrroKnD9-yuR_83wrGyLgC656guPdxT3UABOdYkiIITmMJk-nvEP1Rhw1fE4x17YFTz-2-GJr9ct5OB8FoVNMZkbpDTkXyCrKK2IFW7vOJfEWScHT2KLvJ-RL8nvmFABYsJuDhDWkHpLOi5xs5iZg4x5T-w_mgpxYCaW9RGARDkcfcKJBuhEuyI_)
8. [pypa.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGZp69vbtIZK5s8rn-kCjIa8ezrxejiylKMEJymBzoyMQzW5RFnY-cGadYqZdcU4ER_x3AcHatMmRRcleyU7W-Usdk-d0AyaGeC90f_Ch8vPqD6uRzdBIB057eB3Fcv9Fd2MX8YtOXgxsEWEXVd)
9. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGrChgQGW3nqrWJihRv3aXz9PSwY8H1Jgz9x3G2B8NV1HnUz1G3K8B-2ezCJvIcBc7AlMrprt6YzQwG4ESVoNPY-dXDB5M9mkR8D8QNuQXostl1dy_FoWnXHxGmhJmsj3V-Iu-9NXPd5ms0-2DD01CdhDDsl8xFnQdrmabFnGOl8LucI-0UC2-8IXV4qY_1ouR6YvdU_FHFQga44bIStajBFz8xFIG7oFa0714vjcU=)
10. [pypa.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGS8B4fqZPuiphqnncomE9S40-_8ChKaap6gYgz5Psrgu2y7CPOXD3fIe_Hj_juMUd8T8H91epK_oa12Vg6_BBe78q2Yx7O-XellYFAM6ZcBuEx7tQpv810TwCHHK61c6gVDY0yJGcF0G8VIQ==)
11. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHSGZ3eGl59sqSoim7jfNa_mEfk8yW08EFOwELCN2JzNGQH14Ea-_G0Pjc-QwgCZBGsMzuB002H1l49d64S53A3bYAyeaTDElOWKUlQiM3fOE3Pi1J-DwDoZrBoIMJiVROsoCDkKfpkJinjM4cfrw==)
12. [fedoraproject.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHKYfdGlrdfgx1qXK_7yL2prG4FrMNCWPsKbyAQcb8ViwpZ-GISAjvFfssA3wX62M0onAFWgWG6Qk06uxHS_r3QoTrdstMoJvtJHR4ZIrBKkesmHl_BzwoRs6K8R1DgoGmpQ8cJ61pKqumypdmi81EkWWIQrkOwsrbLgKsA6ejbEDl4SSpS-cAT5nbzxQwfjre8eSBW63w8O3IZpYZbgNM-yZdYHgoRA3CI1w==)
13. [pypa.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGTcXrwz1CfRYJwCBStQ2bj163zozv7NwiPX84_edY2Zv3Vz-jVQCqWk5DL9lGZ8aKzmExCx8GyvNOx3-MGG0x-YnzxZdVwrRFfc4w_-mDgMA_3tVZETQnoY6BMgRmLdvJ6nX9iSP646tRuRXLGsVC-qeYNZuQ=)
14. [kanishk.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFFxI40YFDmazQSSpAdlkR-pKMWTVUEKwetlSBJq1t8Hmv9QLtRgM5i9C0XHNKfkcQwRbmL9FZLP-_JJJv-i5dVO5eJHFi1IxGQ5iTuYWfitSaxEgPlYv1HF5DvRtdhI6__MIqlFrJIUdNXC08=)
15. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEj8KlBpu7M436i2tkY99-o4BEpULnG8QmZhEkC7ufjd2Tvf6r9O-Ki_rlPoVvhNoTNdu5r4tMs-fih04DahkhGQcnZ9GOrr5K-lfpcF_ruUpFen-v7z0bdqd94LxambYfQWFu_ld_q19XzeLarIb6u50-gfdQCJb1ueUfXa-T_hPhIqjoSUyliLZyqbLemsDafYLMTjD5-7LFQtd1ukMdkKmaWhbNJYeU1IsDd)
16. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH6jf8A1cTdR-1y_KiOiVgRfwkcckmcKJJqCtkvXkaWPyTXUtK3pOhwYr09GY8Ub9vNaMb8axAIjkbuo1Bi5ygO5RazvzxqdKsfiAKTYuQXaryTdv45Zg22yo2vNw9Kzp1fRSuhKBtvWfeBhg_b_AFQrZgj9VzNRvsV)
17. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGhdcENo3Rq6miNcCDm6ugnIGZ9XAcAPTtoR-k_Dy6K7ybe3EaFNx7uM_xM_3ezT-dJLXA60-ylZ851ibY5ps4LqA951zuIyjpgywad3Z_r8_yMxdQZTYu7_wIqWk-i7Ph5lNM=)
18. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH4Uy4cakq7uv_dxi29DsxOZLwZvurDSDBwmOCgmqILYe03D6UE-VnwxaOZuvQrG-yB7B7dCSRUOOpa8lg1y2i8bahI4pTJEc-XZ-oe_IYjFOS_--7C9q9BfQE7xI75Pr-AJYqk3TB7qBYAY_mVFfNpkOp6PQPg3TXb-kJH6CmMorxzz_l0FZwU2ZAArrDY9AsjoEYQWQH2wOSEy2ZLgA==)
19. [azalio.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG3ZwpJFdvl0HrslIbadcq0dyhBtqwiN2tkpJhlrWpB86liiRX5_efgyxfK61cvkuVTJyifvZqrsShP3Fqd_v3RmW1eqAgcZrUHZB-48moIFXaM3mYzW9e-yXGAttxvSmXHf49WAK5i_-Ay5TXJMM8JsD2CAYKFnt5t2S5yNQ==)
20. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF2Tw1FBIDuPFVCRTTBM_OLxYIb7djKgr4m_8cgGm_ZlzW2iVsAGvto-jJ6a1RRiWu41diQIoxSUp2zEhL2JfRwbsiKxnr7jV1ZFkTO7T5NF_sX3qh6LE5PHVt3fQBgZPos10XJWnvM_U4fLSOq-8ablny953Jbi22uMvQmd0vqSmmqdGiwsvApunvESks_xXvpSy4NevZ5w8L_JqDzI-ZRyCB8VfBPC57mXBTIsgY=)
21. [geeksforgeeks.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHAhvTAKryAIomxr-RuiX7qPwKyanf2xtwkPjpSrgjQ8AWhPvwFPgtNd_jMdU7tW3nbjtfWhjoZRx3n33mHi1Ko25NJDnZ1UHlR0XOF9am4T1GLl23EkDaDI_LfJcIR5yREgfoNBSXxje5ywbQr1hZkBKfqrIJ1rj8-jvlR6oU=)
22. [ongchinhwee.me](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFZfz6LBaWsdLoQ7mZWBGXpDKg1COq1eVZ6FPirzpYr4EoFLdu2YuXm8sOb5SG6qeoWHGNGZA4ZMPCKrCGOE18ymHLP5GgkQznx978G3Xkew9jK0il2gnARq74oUzfCchu_bPuc8puhSyQK)
23. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE0CN9b7DP6gOgcr89zHWKbEGKVrnrBFVHEsazQMA2xwAqPa3HQY0GSDwbmow4XnHxa4AnawOGBBifLwne5xjvOo8NbE61YNlUc1FOO9Jqgj1gRnn1u)
24. [jfrog.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH3l25w2eRkORYn7EnbGDdgrPfsHCiYLRdchCd_dZ-BeKsi4IhWD3o8j07EJKZUQFkvcKmFo3e2deUw7UxT_ix4lWn9-eEG2drf0pssZGmbmUnabFP6ENB4HY7dc2UPwCXa0a_KxV3a7qryYVBEIO1xS3mNruWds-t1EyJqal9x9uwHLdjn5cE1QQd2i05rzA==)
25. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEbgJQEAXtrX2yPlbDyF8FWul-N3fhpiUYQWHABq67WtljTt7avwssmeigc4PHdN7vfR9xVZhQpLe2CrGAWiT1i3eRNu3tljTfXOUZR5Go2KfbXtAERlR-CJEJrlAc=)
26. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGiLbi9lz5oujrpjJYv7HA-GU8mCb6h8raCL4sdpCRCwVy0UiV1vKBtHhewgI34dxjC61XzIAF-vEAKd-iLO9OIXm5q3B0Cb99S0f-2k98npSIsMfswkfcwwmMyaAqulXcNnFs=)
27. [activestate.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEnRq86AXW2Mo5YVQ75ZYdQjgO7RXwRth5tqsARpCZmuzEFh4NYT-LbW-X0CXyQZ90k4_3TNpbT4aBVm7s-OHECrBMeH6JDgolMXYaXyEMZCcyiRTzHYGubF7hUMvA8GaanCkfExtxxrKQAxj0Uwxs9QeKzKIyoWDrH6U6teNVjKev-KA9Hk7VZUBp2h37u1JNNp9JoEjk=)
28. [linuxsecurity.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGignf0t0BrTlJofliy3jWM3ebjfJ17LK01k_YGz4sl3sjNUbP3JKTsD3bddj_TASyartoFmmb6zlBAZZu8DGzA1nHs_ggtm5Tc2qiI4TYbE91qoUCeInmkiYxGivZfW6F4DEIwak1ovDEbntUy6JPnu_P-0OvhRnam-n1vsrFgsRMOzEqi7uBpJze8fuIWStfOjSw5bHFx)
29. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG0Fek6fg73Q7mFbenR8wJQqASGbKBYn5bnbHskD5tGEzIhcVjVPyzmnHF9XtCa66IOIJD3b_hna3TytcCTk7bG1TK0Z-iv5B0TrPGfncdl85iAWHsnsQ==)
30. [farmdev.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHuYpVOlkNidKzT0qcZ4Nek_TVUWQLw3njIOQPd3_sRV9Ci6-CsEbvuAE9CPDftDwt_N2vgNuCLQ0ZjhRTA6A8o3Mlam6TSU0fI2Cjw4k1S9Sh_EUDFM92CXIkDarvQR-GEjiLfab5S-WAdRBPf3py9209N1GTWwVU3AwmI98z3raQONcsJ)
31. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF9cmuUVOoZBw-Q_kTEnvN-O0w7P4AD72mtUl-PTPoMH6AmAPOyum4ZmUtU7QJdWL7o-71oIk4x3K9RrCnP3acnUX0UMzmHhiX3pGyFL-HwiJ8hEQfZNBdu-Y4a_HY=)
32. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGNT29CLSi7sUnBJ30XlbfSElbIOzoEI_kl3EhRx8DDhCRo7_Ycc66qME4I8f12yc6AawjQ1g_uKCJTPq4MkGNb3C6szJtCjIPhR-WacsEvfLo-NqwYUqnSdxrAI4tE_H9MfRMm4_biuktDEy4BHevQYrKMCba7mGAmjocU5-QyJNQUG9N9Hg7T47FGQkuYOsA4ww7c3UOzJR9ArsyqhwA41C9wnwCkzKc=)
33. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGkeffbVe9ZNaEEtXByo_ZcrAla0cjz7V9OYidBwjGG2pkG_cv-aXu-8L5IkovlAtokGdQ8Qfgo73zTiaeTtDjKXUBxCNI5Fu0aDaeKfGwRdw9UuBaD6gP1iGiMpTAgKlw8UyNOb7WY4yfZ9S_TJzerXI_spCLeHZbtdwF__vqIJV4=)
34. [geeksforgeeks.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGulRRbfU3XSEAMPjSZRviFIDMCvu29jeAV0WoP_yuCfl1uWYmqDDAGROw9FiRYmhNC03mbVpu_IAN0ZB7Zo36D73p5i4V42CM7apWKL_Fv6M4Uha6mGllu9JjkML2U9m4bODVo_iSdRtrYqDqF1uwwPHZ2-U0i1MPlnw3mK9JZ0j6USJJmVMOa3GUZhg==)
35. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFGsSrX_FjTO5kOZgq7yW-7Kx7hMREIG8zr3172-LBeuh678lJ-_Hc4OMpKEatyjdTeD_XNFn9oIjw5Xd23JzFN9uw0wVT-PzQVErV0MfGxI31xhQ99FosVOh1y4ys0LlaL)
36. [realpython.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGI4pbHTVYQ2HxEEasndTPyst1wLJ3i2hmfGA3BSwYkwWxmZ9tQz2-qfQHqQ4K5KuRYAPKYKH89Ie9rpXltmpc-1MQLEWg7QRKTCU4dFpbklp5j8F3O1FJUXw==)
37. [python.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFghzBXeKupoLMP927cGfQW_aDMAJSfRWgr1IXS-eyJDKiZkpZjKNWfOAu4BkGKXZ_0nbxI8zQuZynKNhwte7YWUZMNGvU-9HdYxeQaDm_PAbMg23B1irsCXC6GnSZoMga0l94X_cciXaikbufYHsmit00_IfPTNYsFUgfChdZ5CLRDq_5Nt5OB)
