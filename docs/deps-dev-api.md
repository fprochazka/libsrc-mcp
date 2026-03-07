# Comprehensive Guide to the deps.dev API v3 for Software Supply Chain Intelligence

The Google Open Source Insights (deps.dev) API v3 is a powerful tool for analyzing the structure, security, and construction of open-source software packages. By aggregating data from major packaging ecosystems, security advisory databases, and source code hosts, it allows developers and researchers to map published artifacts (packages) back to their source code repositories. This capability is critical for supply chain security, enabling the verification of provenance, the assessment of project health (via OpenSSF Scorecards), and the detection of vulnerabilities in transitive dependencies.

**Key Points:**
*   **Core Function:** The API serves as a bridge between abstract package versions (artifacts) and concrete source code repositories (GitHub, GitLab, Bitbucket), utilizing varying levels of provenance verification.
*   **Ecosystem Coverage:** It currently supports seven major ecosystems: **npm, Go, Maven, PyPI, Cargo, NuGet, and RubyGems**.
*   **Mapping Reliability:** The reliability of mapping a package to a source repo varies significantly by ecosystem. Go is highly reliable (due to its source-based nature), while ecosystems like npm and PyPI rely heavily on unverified metadata, though recent integrations with SLSA (Supply-chain Levels for Software Artifacts) attestations are improving this.
*   **Data Structure:** Dependency graphs are returned as flat lists of nodes and edges rather than nested trees, providing a fully resolved graph that mirrors the package manager’s installation logic.
*   **Access:** The API is free, requires no authentication for standard HTTP usage, but enforces rate limits (specifically on batch operations) to prevent abuse.

---

## 1. Supported Ecosystems and System Identifiers

To interact with the deps.dev API, one must use the correct system identifier strings. These identifiers are case-insensitive in some contexts but are strictly normalized in the API response data. The API currently supports seven distinct package management systems.

| Ecosystem | Language | API System Identifier | Package Name Format / Notes |
| :--- | :--- | :--- | :--- |
| **Go** | Go | `GO` | typically a URL-like path (e.g., `github.com/gin-gonic/gin`) |
| **npm** | JavaScript/TS | `NPM` | Scoped packages must be URL-encoded (e.g., `@types/node` becomes `%40types%2Fnode`) |
| **PyPI** | Python | `PYPI` | Normalized according to PEP 503 (e.g., `Flask`) |
| **Maven** | Java/JVM | `MAVEN` | Format: `GroupID:ArtifactID` (e.g., `org.apache.logging.log4j:log4j-core`) |
| **Cargo** | Rust | `CARGO` | Standard crate names (e.g., `serde`) |
| **NuGet** | .NET | `NUGET` | Case-insensitive (e.g., `Newtonsoft.Json`) |
| **RubyGems** | Ruby | `RUBYGEMS` | Standard gem names (e.g., `rails`) |

**Source:** [cite: 1, 2, 3]

---

## 2. API Endpoints: Patterns, Parameters, and Schemas

The API is accessed via HTTPS. The base URL for the stable v3 API is `https://api.deps.dev/v3`. For experimental features (like batch queries), the `v3alpha` endpoint is used: `https://api.deps.dev/v3alpha`.

All path parameters (system, name, version) must be **URL-encoded** [cite: 1, 4].

### 2.1 GetPackage
Retrieves metadata about a package, including a list of all available versions.

*   **URL Pattern:** `GET /v3/systems/{system}/packages/{name}`
*   **Request Parameters:** Path parameters only.
*   **Response Schema:**
    *   `packageKey`: The canonical system and name.
    *   `versions`: An array of objects containing:
        *   `versionKey`: The specific version string.
        *   `publishedAt`: ISO 8601 timestamp.
        *   `isDefault`: Boolean (often the latest stable version).

**Example:**
```bash
curl 'https://api.deps.dev/v3/systems/npm/packages/react'
```

### 2.2 GetVersion
The most critical endpoint for source mapping. It retrieves details for a specific package version, including licenses, links, and provenance.

*   **URL Pattern:** `GET /v3/systems/{system}/packages/{name}/versions/{version}`
*   **Response Schema (Key Fields):**
    *   `licenses`: Array of SPDX license expressions.
    *   `advisoryKeys`: IDs of security advisories affecting this version.
    *   `links`: Array of unverified metadata links (Homepage, Repo, etc.).
    *   **`relatedProjects`**: Array of mapped source code repositories (Crucial for mapping).
    *   `slsaProvenances`: (npm only) Verifiable build provenance.
    *   `attestations`: Signed metadata verifying the package origin.

**Example:**
```bash
curl 'https://api.deps.dev/v3/systems/maven/packages/com.google.guava%3Aguava/versions/31.1-jre'
```

### 2.3 GetProject
Retrieves details about a source code repository (GitHub, GitLab, Bitbucket).

*   **URL Pattern:** `GET /v3/projects/{projectKey}`
*   **Request Parameters:** `projectKey` must be double URL-encoded if it contains slashes (e.g., `github.com%2Fgoogle%2Fguava`).
*   **Response Schema:**
    *   `scorecard`: OpenSSF Scorecard security metrics.
    *   `starsCount`, `forksCount`, `openIssuesCount`.
    *   `license`: License detected in the repo.
    *   `ossFuzz`: Fuzzing status (if applicable).

### 2.4 GetDependencies
Returns the *resolved* dependency graph.

*   **URL Pattern:** `GET /v3/systems/{system}/packages/{name}/versions/{version}:dependencies`
*   **Response Schema:**
    *   `nodes`: Flat list of packages in the graph.
    *   `edges`: Connections between nodes (indices pointing to the `nodes` array).

### 2.5 GetAdvisory
Retrieves details about a specific security advisory (OSV).

*   **URL Pattern:** `GET /v3/advisories/{advisoryId}`
*   **Example ID:** `GHSA-vh95-rmgr-6f4m`

### 2.6 Query
Search for packages by specific hash values (identifying mystery binaries) or version attributes.

*   **URL Pattern:** `GET /v3/query`
*   **Query Parameters:** `hash.type` (SHA256), `hash.value` (base64 encoded).

**Source:** [cite: 1, 4, 5]

---

## 3. Mechanisms of Source Repository Mapping

The deps.dev API employs two distinct methods to map a package artifact to its source code. Understanding the difference between these is vital for assessing reliability.

### 3.1 The `links` Array (Unverified Metadata)
This array contains URLs scraped directly from the package manifest (e.g., `package.json`, `pom.xml`, `Cargo.toml`).
*   **Field:** `links[].url`
*   **Label:** `links[].label` (e.g., "SOURCE_REPO", "HOMEPAGE", "ISSUE_TRACKER").
*   **Reliability:** **Low to Moderate.** This is self-declared data by the package author. It may be outdated, broken, or intentionally misleading (pointing to a popular repo that is not actually the source).
*   **Source:** [cite: 1, 4]

### 3.2 The `relatedProjects` Array (Inferred & Verified)
This field represents the API's attempt to intelligently map the package to a specific project (repository) on a supported code host.
*   **Field:** `relatedProjects[].projectKey.id` (e.g., `github.com/expressjs/express`).
*   **Field:** `relationProvenance`
    This enum tells you *how* the API determined the link.
    *   **`SLSA_ATTESTATION`**: The highest trust level. The package contains a cryptographically signed attestation linking the binary to a specific build workflow and git commit.
    *   **`GO_ORIGIN`**: High trust. In the Go ecosystem, the package name *is* the source URL.
    *   **`PYPI_PUBLISH_ATTESTATION`**: Verified link between a PyPI release and a GitHub repository via Trusted Publishing (OIDC).
    *   **`RUBYGEMS_PUBLISH_ATTESTATION`**: Similar to PyPI, using OIDC for RubyGems.
    *   **`UNVERIFIED_METADATA`**: The API parsed the manifest (same as `links`) but normalized and resolved the repo URL.
*   **Source:** [cite: 1, 4, 5, 6]

---

## 4. Reliability of Source Mapping

The reliability of the mapping depends entirely on the `relationProvenance`.

### 4.1 Verified vs. Unverified Stats
*   **Go:** Near 100% reliability for `GO_ORIGIN` because the ecosystem enforces source location in the module path [cite: 5].
*   **npm/PyPI (Legacy):** historically relied on `UNVERIFIED_METADATA`. Research indicates that while over 99% of packages might link to a repo, the number of *verified* links is significantly lower [cite: 7].
*   **SLSA & Sigstore:** The introduction of SLSA attestations (starting with npm) allows for cryptographic verification. However, adoption is currently low (estimated <1% of total packages), limited mostly to packages using specific GitHub Actions workflows [cite: 8, 9].
*   **Gaps:** Packages that are deprecated, deleted from the registry, or published purely from a local machine (without CI/CD integration) often lack verifiable source links. Private/Corporate packages are not covered at all.

### 4.2 Provenance Types Explained
1.  **`SLSA_ATTESTATION`**: Verified via Sigstore. Guarantees the artifact was built from `commit X` in `repo Y`.
2.  **`GO_ORIGIN`**: Implicitly verified by the Go toolchain's proxy design.
3.  **`UNVERIFIED_METADATA`**: Heuristic. The API checks if the URL in `package.json` looks like a GitHub repo, but cannot guarantee the artifact was actually built from it.

---

## 5. Supported Git Hosting Services

The `GetProject` endpoint and `relatedProjects` mapping strictly support the following three major hosting platforms. If a package is hosted on a self-hosted Git server or a minor platform (e.g., SourceForge), it will generally not appear in the `relatedProjects` or `GetProject` response, though it may appear in the raw `links` array.

1.  **GitHub** (`github.com`)
2.  **GitLab** (`gitlab.com`)
3.  **Bitbucket** (`bitbucket.org`)

**Source:** [cite: 1, 10, 11]

---

## 6. The GetProject Endpoint: Repository Intelligence

When you have a valid `projectKey` (e.g., `github.com/lodash/lodash`), calling `GetProject` returns deep intelligence about the repository itself.

**Data Fields returned:**
*   **OpenSSF Scorecard:** A comprehensive security analysis object.
    *   `score`: Overall security score (0-10).
    *   `checks`: Individual results for "Binary-Artifacts", "Code-Review", "Maintained", "Pinned-Dependencies", etc.
*   **OSS-Fuzz:** If the project is enrolled in Google's OSS-Fuzz program, this object details fuzzing coverage and regression status [cite: 3, 12].
*   **Metadata:**
    *   `starsCount`: Proxy for popularity.
    *   `forksCount`: Proxy for community engagement.
    *   `openIssuesCount`: Proxy for maintenance burden.
    *   `license`: The detected license of the source code (which may differ from the package license).

**Source:** [cite: 1, 4]

---

## 7. Operational Details: Rate Limits and Authentication

### 7.1 Authentication
The deps.dev API v3 is public.
*   **HTTP:** No API key or authentication token is required for standard queries.
*   **gRPC:** Accessing via gRPC might require specific setups, but the HTTP/JSON interface is open [cite: 1, 11].

### 7.2 Rate Limits
There is no officially published "requests per second" limit for simple GET requests documented in the public terms. However:
*   **Batch Limits:** The batch endpoints (`GetVersionBatch`) strictly enforce a limit of **5,000 items per request**. Exceeding this returns a `400` error [cite: 4].
*   **Abuse Prevention:** Standard IP-based rate limiting (HTTP 429) applies if excessive scraping is detected.

### 7.3 Data Freshness
The service continuously crawls upstream registries (npm, Maven Central, etc.) and GitHub. Updates are generally reflected daily, though propagation of new versions can take a short period to appear in the resolved graphs [cite: 13].

---

## 8. GetDependencies: Structure and Format

The `GetDependencies` endpoint does **not** return a nested JSON tree. Instead, it returns a graph structure to efficiently handle shared transitive dependencies (diamond dependencies).

### 8.1 Response Format
The response contains two main arrays:
1.  **`nodes`**: An indexed array of packages. `nodes` is the root package (the one you queried).
2.  **`edges`**: An array of connections.
    *   `fromNode`: Index in the `nodes` array (the parent).
    *   `toNode`: Index in the `nodes` array (the child).
    *   `requirement`: The version constraint string (e.g., `^1.2.0`).

### 8.2 Resolution
The API performs **dependency resolution**. It does not just list the manifest file. It calculates the specific versions that would be installed by the native package manager (e.g., `npm install`, `go get`) on a fresh Linux system [cite: 5, 14].

---

## 9. Limitations and Coverage Gaps

*   **Private Packages:** The API **does not** support private packages or internal corporate registries. It only indexes public, open-source data [cite: 1, 2].
*   **Maven Gaps:** While it covers Maven Central, Google Maven, and Gradle Plugins, it may miss artifacts hosted on smaller, niche Maven repositories [cite: 1].
*   **Go Gaps:** Only collects modules fetched via `proxy.golang.org` or declared as dependencies of other modules [cite: 1].
*   **Unverified Mapping:** For ecosystems like npm and Maven, if `relationProvenance` is `UNVERIFIED_METADATA`, the source repo is a "best guess" based on the manifest strings. It is possible for a malicious package to declare a legitimate project's repo as its own (Typosquatting/Starjacking) [cite: 15].

---

## 10. Batch Queries

To query multiple packages efficiently, use the `v3alpha` batch endpoints (migrating to `v3` stable). These use `POST` instead of `GET`.

### 10.1 Endpoints
*   `POST /v3alpha/versionbatch`
*   `POST /v3alpha/projectbatch`

### 10.2 Capability
*   Allows querying up to **5,000** identifiers in a single HTTP call.
*   Useful for scanning a whole `package.json` or `go.mod` file in one go to check for licenses or advisories.
*   Results are paginated if the response is too large.

**Source:** [cite: 4, 12]

---

## 11. Practical Guide: Mapping deps.dev to a Cloneable Git URL

To map a deps.dev `projectKey` to a `git clone` URL, you must parse the ID string. The API standardizes IDs for the three supported hosts.

| Project Key ID Pattern | Constructing the Clone URL |
| :--- | :--- |
| `github.com/user/repo` | `https://github.com/user/repo.git` |
| `gitlab.com/group/project` | `https://gitlab.com/group/project.git` |
| `bitbucket.org/user/repo` | `https://bitbucket.org/user/repo.git` |

**Note on Versions:** The `GetVersion` response includes a `commit` hash in the `attestations` or `slsaProvenances` field if verified. To get the exact code for that version, you should clone the repo and `git checkout` that specific commit hash.

---

## Concrete API Call Examples

### Example 1: Full Source Mapping Workflow (curl)

**Objective:** Find the source repo for the npm package `express`, version `4.18.2`, and check its security scorecard.

**Step 1: Get Version Details to find the Project Key**
```bash
# Note the encoding: @ is %40 (not needed here but good practice), / is %2F
curl -s "https://api.deps.dev/v3/systems/npm/packages/express/versions/4.18.2" > express_version.json
```

**Step 2: Parse Response (Conceptual JSON)**
```json
{
  "versionKey": { "system": "NPM", "name": "express", "version": "4.18.2" },
  "relatedProjects": [
    {
      "projectKey": { "id": "github.com/expressjs/express" },
      "relationType": "SOURCE_REPO",
      "relationProvenance": "UNVERIFIED_METADATA"
    }
  ]
}
```

**Step 3: Get Project Health (using the ID found above)**
```bash
# ID "github.com/expressjs/express" must be URL encoded
curl -s "https://api.deps.dev/v3/projects/github.com%2Fexpressjs%2Fexpress" > express_project.json
```

**Step 4: Parse Project Response (Conceptual JSON)**
```json
{
  "projectKey": { "id": "github.com/expressjs/express" },
  "scorecard": {
    "overallScore": 8.9,
    "checks": [
      { "name": "Code-Review", "score": 10 },
      { "name": "Vulnerabilities", "score": 10 }
    ]
  },
  "starsCount": 63000,
  "license": "MIT"
}
```

### Example 2: Batch Query for Multiple Packages

**Objective:** Get info for `react` (npm) and `gorilla/mux` (go) in one call.

```bash
curl -X POST "https://api.deps.dev/v3alpha/versionbatch" \
     -H "Content-Type: application/json" \
     -d '{
           "requests": [
             {
               "versionKey": {
                 "system": "NPM",
                 "name": "react",
                 "version": "18.2.0"
               }
             },
             {
               "versionKey": {
                 "system": "GO",
                 "name": "github.com/gorilla/mux",
                 "version": "v1.8.0"
               }
             }
           ]
         }'
```

### Example 3: Get Dependencies Graph

**Objective:** See the dependency graph for `requests` (PyPI).

```bash
curl -s "https://api.deps.dev/v3/systems/pypi/packages/requests/versions/2.31.0:dependencies"
```

**Response Snippet:**
```json
{
  "nodes": [
    { "versionKey": { "system": "PYPI", "name": "requests", "version": "2.31.0" } },
    { "versionKey": { "system": "PYPI", "name": "charset-normalizer", "version": "3.1.0" } },
    { "versionKey": { "system": "PYPI", "name": "idna", "version": "3.4" } }
  ],
  "edges": [
    { "fromNode": 0, "toNode": 1, "requirement": ">=2,<4" },
    { "fromNode": 0, "toNode": 2, "requirement": ">=2.5,<4" }
  ]
}
```

**Sources:**
1. [Link](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGrlJLiPCpk5-GBupl_FQU9ZTFTgps1JDFjUKDNX8aSOwZreHg3AqMhB3tGhypvYyvaQjW5lfhi2lWBXPwMp860sYHMlqIPQv_M19fVqhcrVyaKgw==)
2. [lobehub.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHrsT5kyFAIsTd8VZNxO2eIkSE4a1xtpwvQ4TEioQqgz15z3prY18NMp5hZiqTdy4ek2452-2-2tPBTKsBzzdJGPShY179ddjnXgNqljaUCxlkEypiMWiQXpNTWmEtoNHZPmF31dqQJvXMGJuSTFPHSFXQR)
3. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH7T5nibmJH38_VLeWVZwgR7XT1rzP_J2u-hgfh113mLnMcwYAouocwR47QCErKShBxQL9ZTFaSwpoMlHeDFLFKBsjUYLOH4EmU2eXh)
4. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEcRAWI-DEQDNl1afcp5aayfI-ZRmNmGeYMHEwbho7CVExBMWvhXfsineNg0_QXl6lAkMbBUFPo7MC8R_TcLj0-EZKfFnZp_SUoyHoTBOOj2wfVDjVvD22z)
5. [go.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH_G37I_12rNfYmv5WQWXDDbJ4ieu9qS5vkZ_qYuuwKISy2MM6EJpCSNQ9BiS8ATw-2owfPXdJJlHUGakztlU0_kAmwDPQ6xUoXwdneANUU_Ap-quNPzwqb)
6. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFZzD_ue7ND3Zpj6CAG7ivjSrwQ8_KK60vV-f-J5OpdQ7773iqF-dXl-y0l9FUJCWXMN2ukAq2ij8_8GmmUElY_vg_SUaePS6xInA2keytaPQZQmGYCOs3osKltHb0f_zRyWN58vcuBsdm_mQF7BEWciLlHTN-6oGQaiYJmFq9sjei8tysUIUFj)
7. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGFqduKMW8nGQLIEGe0cM9AGaT5aWTaQT9xzbacaal8JRfJos31AbzXqWBwoYuA3r0GRNgWOcdllFgRPqJ1HnG6XAC7_52sjhpEpYo-L1VVIrl_uM0CNUAwgV8CJM9QjdJAUsA3boDz9ea0EGKORdaPF_g8zIdO)
8. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH4rHvL-wG3bxcERlIhJXvXbz_bvQjSh5MCZtXw-sqI5kN5qxJkyR9C9eNrGtbC8rVHByPwgNUijxdNJ3UG_NULyWmCNXvDZ1xiiZ_zyhw3HAztwx2CqfPC7ZDJ)
9. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFd4-zGk1Gt5S2x91yBpCoxyJDGjayOoeY8s7iF6cHGJqgorKzeJitZddPFk5w652JliYhDeN_HGiwyosUt3lztZQtFiBWFEQfAsmwmFP4ansO9e8MXV1-0O05GsSK2s2y94POGLqV7cVG5NLDyrXG_FKFQrRV92j3eD-aSYf5DiVSUO4_PVLA=)
10. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEWO_c1Dc5rQBvq4nGhLM3cAr5a9cG5qP7lEOKiFb0FKpoqwgX11Ealwyj4ilGnGnc8SwDcVURJnX63JO1Y-NTcglYXdOwCuUH1mIGt)
11. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEhUAKFS9uh5pLPc99LfDU1mz2_jh1Dwu8w3DsabJAgQXngYkG41WeHl24dZ3KkIq75xsnQZgEwxYYuldjp6eJAZIsj4j0xbqHza1q62uHEr8ukGRBY8hVu)
12. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEVEYDr8gR4Y7QipxxmRnjZ7gKkYaHBbT0bbbNgvzMUC8ROE0nZFNnss2F9qAzumXtXxaIgEKNZEaS1gfh7A3hIVmtf5S85_KJOKFxOamJwIpxahw==)
13. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHaXAQnlRnj3WdCTeUE6uRihHRmPhald2FRxU8IGxbgF3UDrUIQgSdSCH14VMolHeanXuGWFLljeEUHIg40YR4aWktVfvzyqXXWT_Pi4Bas4XDuAwqUR18irNAqMeYKDw==)
14. [neo4j.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFJDbrsFmdskvNt99YjjRGcTohNcIF1DnRkQhAcC0Puqegc55Qr1itWVX1HFu1lYhKbCG0gSFcdbVreEqzy4YTzkJohH5cxGMNaVkWXRSjFCIflh_NcBAeUlU_5YgiY2t93MQpNG9j7CpTtRPaYBwcOa3NCxAD_vjNkgvZPyIPE)
15. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGWW42lHTvq9eq5TLZDanmw7Kjg9z3KakRi6_Hyl5MW9qzp8xAOyo9_GqMZOCPdFa2DQbp9UVSNyRlZsBFYqg8WQ8ghDdl9RiobRsrE0t9ny5yoeL2dv6rqFA==)
