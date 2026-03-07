# Programmatic Resolution of Maven Dependencies and Source Repository Mapping

### Executive Summary

Extracting a complete, accurate dependency tree and mapping Maven artifacts to their original source code repositories is a multi-step process that bridges build automation with metadata analysis. The most reliable method for dependency extraction utilizes the Maven Dependency Plugin (`mvn dependency:tree`), specifically version 3.7.0 or later, which supports native JSON output. This approach leverages Maven’s internal resolution engine to handle complex tasks such as property interpolation, parent POM inheritance, and Bill of Materials (BOM) imports—tasks that are notoriously error-prone when attempted via static parsing of `pom.xml` files.

For source repository discovery, the standard `<scm>` metadata within POM files serves as the primary data source, though it often requires normalization. While the Maven Central Search API allows for artifact discovery, it does not directly expose SCM metadata in its search results, necessitating the retrieval and parsing of the raw POM files or the use of specialized aggregation APIs like Google’s `deps.dev`. Mapping artifacts to specific Git commits or tags relies on conventions (e.g., `v1.0.0` or `artifactId-version`), but deviations are common, requiring heuristic fallback strategies.

---

## 1. Extracting Dependency Trees via Maven CLI

The primary tool for extracting dependencies programmatically is the `maven-dependency-plugin`. While older versions relied on parsing text or DOT output, modern workflows should prioritize JSON for machine readability.

### 1.1 Command-Line Invocations

To extract the dependency tree, the `dependency:tree` goal is preferred over `dependency:list` as it preserves the hierarchical structure of transitive dependencies.

**Basic Invocation (Text Output):**
```bash
mvn dependency:tree -DoutputFile=dependencies.txt
```

**Machine-Readable Invocation (JSON):**
*Requires `maven-dependency-plugin` version 3.7.0+.*
```bash
mvn dependency:tree -DoutputType=json -DoutputFile=dependency-tree.json
```

**Alternative Formats (DOT/GraphML):**
For visualization or graph analysis tools:
```bash
mvn dependency:tree -DoutputType=dot -DoutputFile=dependencies.dot
mvn dependency:tree -DoutputType=graphml -DoutputFile=dependencies.graphml
```

### 1.2 Output Formats and Fields

#### JSON Format (Recommended)
The JSON output provides a nested structure representing the resolution graph.
*   **Structure:** Root object containing a `children` array.
*   **Fields Included:**
    *   `groupId`: The group identifier (e.g., `org.apache.logging.log4j`).
    *   `artifactId`: The artifact identifier (e.g., `log4j-core`).
    *   `version`: The resolved version after conflict resolution.
    *   `scope`: The classpath scope (e.g., `compile`, `test`, `provided`).
    *   `type`: Packaging type (e.g., `jar`).
    *   `classifier`: (Optional) Artifact classifier (e.g., `sources`).
    *   `optional`: Boolean indicating if the dependency is optional.

**Example JSON Snippet:**
```json
{
  "groupId": "com.example",
  "artifactId": "my-app",
  "version": "1.0.0",
  "type": "jar",
  "children": [
    {
      "groupId": "org.springframework",
      "artifactId": "spring-core",
      "version": "5.3.10",
      "scope": "compile",
      "children": []
    }
  ]
}
```

#### DOT and GraphML
*   **DOT:** A directed graph description language. Useful for generating images via Graphviz but requires parsing for programmatic use. Nodes are labeled with `groupId:artifactId:type:version`.
*   **GraphML:** XML-based graph format. Useful if importing into graph databases (e.g., Neo4j, Gephi) [cite: 1, 2].

---

## 2. Handling Multi-Module Projects (Reactor Builds)

Multi-module projects (Reactor builds) present specific challenges because `mvn dependency:tree` executes separately for each module.

### 2.1 The Reactor and File Overwriting
By default, if you specify `-DoutputFile=deps.json` in the root of a multi-module project, every module will write to that same filename relative to its own directory, or if an absolute path is used, they may overwrite each other sequentially.

### 2.2 Aggregation Strategy
To capture the entire tree of a multi-module project into a single file or coherent set of files:

1.  **Append Mode:** Use `-DappendOutput=true` to prevent overwriting.
    ```bash
    mvn dependency:tree \
      -DoutputType=json \
      -DoutputFile=/absolute/path/to/full-tree.json \
      -DappendOutput=true
    ```
    *Note: The resulting file may contain concatenated JSON objects (multiple root objects), which is not valid single-root JSON. The parser must handle multiple JSON objects in a stream.*

2.  **Per-Module Files:** Allow default behavior where each module writes `dependency-tree.json` to its own `target/` directory, then aggregate programmatically.
    ```bash
    mvn dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
    ```
    *Post-process:* Traverse all `*/target/dependency-tree.json` files.

### 2.3 Handling "Not Installed" Failures
In a fresh checkout, `mvn dependency:tree` might fail if submodule A depends on sibling submodule B, but B hasn't been installed to the local repository (`~/.m2`).
*   **Solution:** Use the `package` or `install` phase to ensure artifacts exist, or rely on the reactor's resolution if the dependency plugin is executed in the same run as the build [cite: 3, 4].
*   **Command:** `mvn package dependency:tree` (builds artifacts so they are available for tree generation).

---

## 3. Resolving Effective Versions

Static analysis often fails to determine the correct version due to Maven's dynamic features. The `dependency:tree` command solves this by leveraging the effective POM.

### 3.1 Interpolation and Inheritance
*   **Properties:** Versions defined as `${spring.version}` are resolved to literals.
*   **Parent Inheritance:** Dependencies defined in a Parent POM are merged into the child.
*   **Dependency Management (BOM):** Versions omitted in the `<dependencies>` section but defined in `<dependencyManagement>` (often via BOM imports) are fully resolved.

### 3.2 Extracting the Effective POM
If debugging resolution logic is required, generating the effective POM shows the final merged XML:
```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

---

## 4. Static Parsing of `pom.xml` (Without Maven)

Parsing `pom.xml` without a running Maven installation is possible but inherently limited.

### 4.1 Feasibility and Tools
*   **XML Parsers:** Standard XML parsers can read the file, but cannot resolve inheritance or properties.
*   **Libraries:**
    *   **Java:** `maven-model` library (part of Maven core) can be used programmatically to read POMs.
    *   **Node.js:** Packages like `node-pom-parser` exist but typically only parse the XML structure without resolving complex Maven logic [cite: 5].

### 4.2 Limitations
1.  **Interpolation:** You cannot resolve `${project.version}` or custom properties without parsing the entire hierarchy and `settings.xml`.
2.  **Inheritance:** You must locate and parse the `<parent>` POM, which may be a relative path or require fetching from a remote repository.
3.  **Dynamic Profiles:** Dependencies activated by specific JDK versions or OS profiles (`<activation>`) cannot be determined statically without mimicking the environment.

**Conclusion:** Static parsing is sufficient for identifying declared identifiers (groupId/artifactId) but unreliable for resolving exact versions or the full transitive tree.

---

## 5. Extracting Source Code Repositories

To link a binary artifact to its source code, one must extract metadata from the POM or external registries.

### 5.1 The `<scm>` Element
The primary location for source control metadata is the `<scm>` tag in the POM [cite: 6, 7].

**XML Path:** `/project/scm`
**Key Fields:**
*   `connection`: Read-only access (e.g., `scm:git:git://github.com/user/repo.git`).
*   `developerConnection`: Write access (e.g., `scm:git:ssh://github.com:user/repo.git`).
*   `url`: Browsable web URL (e.g., `https://github.com/user/repo`).

### 5.2 Inheritance Issues
SCM URLs are inherited. If a child module does not override the `<scm>` element, it inherits the parent's URL. Maven attempts to append the artifactId to the parent URL automatically, which often results in incorrect URLs (e.g., `github.com/parent/child-module` when the repo is actually a mono-repo at `github.com/parent`).

---

## 6. Maven Central REST API

The Central Repository Search Engine (Solr) provides coordinates but limits deep metadata retrieval [cite: 8].

### 6.1 Search Endpoint
**URL:** `https://search.maven.org/solrsearch/select`
**Parameters:**
*   `q`: Query string (e.g., `g:"com.google.guava" AND a:"guava"`).
*   `wt`: Output format (`json` or `xml`).
*   `core`: `gav` (Group Artifact Version) for specific versions.

**Example Request:**
```bash
curl -s "https://search.maven.org/solrsearch/select?q=g:com.google.guava+AND+a:guava&wt=json"
```

### 6.2 Response Format
The JSON response includes:
*   `id`: `groupId:artifactId:version`
*   `g`, `a`, `v`: Individual coordinates.
*   `timestamp`: Upload time.
*   `ec`: Extension/packaging (e.g., `.jar`, `.pom`).

**Limitation:** The Search API response **does not** contain the SCM URL. To get the SCM URL, you must download the POM file directly using the coordinates found in the search result.

**Constructing POM URL:**
`https://repo1.maven.org/maven2/{groupId}/{artifactId}/{version}/{artifactId}-{version}.pom`
*(Replace dots in groupId with slashes).*

---

## 7. Mapping Artifacts to Source Repositories

### 7.1 Mapping Strategy
1.  **Direct SCM Parsing:** Download the POM from Maven Central and parse `/project/scm/url`.
2.  **Parent Traversal:** If the POM has a parent and no SCM tag, fetch the parent POM and check its SCM tag.
3.  **Heuristics:** If SCM data is missing, search GitHub/GitLab APIs using the `artifactId`.

### 7.2 Version Tagging Conventions
Once the repository is found, mapping the specific Maven version (e.g., `1.2.3`) to a Git tag requires guessing the convention [cite: 9, 10, 11].

**Common Tag Patterns:**
1.  **Exact Match:** `1.2.3`
2.  **Prefix 'v':** `v1.2.3` (Very common in SemVer).
3.  **Release Prefix:** `release-1.2.3`.
4.  **Maven Release Plugin Default:** `@{artifactId}-@{version}` (e.g., `my-library-1.2.3`).

---

## 8. The deps.dev API

For a robust, pre-computed solution, Google's `deps.dev` API is superior to manual parsing. It resolves dependencies and maps source repositories using its own massive dataset [cite: 12].

### 8.1 API Usage
**Endpoint:** Get Version Details
`GET https://api.deps.dev/v3/systems/maven/packages/{groupId}:{artifactId}/versions/{version}`

**Example:**
`https://api.deps.dev/v3/systems/maven/packages/com.google.guava:guava/versions/31.1-jre`

### 8.2 Response Data
*   **`links`**: Array containing keys like `SOURCE_REPO`, `HOMEPAGE`.
*   **`dependencies`**: Fully resolved dependency graph.
*   **`licenses`**: License information.

**Example JSON Response Field:**
```json
"links": [
  {
    "label": "SOURCE_REPO",
    "url": "https://github.com/google/guava"
  }
]
```
This API eliminates the need to manually download POMs, parse XML, and handle SCM inheritance logic.

---

## 9. Conclusion: Recommended Workflow

To build a tool that resolves Maven dependencies and finds source repositories:

1.  **For Local Projects:** Use `mvn dependency:tree -DoutputType=json` to get the accurate, resolved dependency graph including local modifications.
2.  **For Remote/Public Artifacts:** Query the **deps.dev API** first. It provides the SCM URL and resolved dependencies immediately.
3.  **Fallback:** If deps.dev is insufficient, use the **Maven Central Search API** to find coordinates, download the **POM file** from `repo1.maven.org`, and parse the `<scm>` tag, applying standard tag naming heuristics to locate the specific release commit.

### Summary Table: Tools & Commands

| Task | Recommended Tool/Command | Key Flags |
| :--- | :--- | :--- |
| **Extract Tree** | `mvn dependency:tree` | `-DoutputType=json`, `-DoutputFile=...` |
| **Multi-Module** | `mvn dependency:tree` | `-DappendOutput=true` |
| **Find SCM URL** | **deps.dev API** | `/v3/systems/maven/packages/...` |
| **Find Metadata** | **Maven Central API** | `solrsearch/select?q=...` |
| **Mapping Strategy** | POM Parsing + Tag Heuristics | Check `v{ver}`, `{artifactId}-{ver}` |

**Sources:**
1. [baeldung.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFd8Cm-kpQwGVmyIohUjbjqYpY1IxzcveZMlEmIW1mWWdA2BSAKV48stTdAGzmnvr63DJKM31wZM0WYcD03DcWs5K24hlA9UUFDOsvAIo_NWeZFmWfnuLpjeIRZuk0HR0zQfRtsdA==)
2. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGkksN2lR6BnDk_A0QTE5eiQGBb5dJFIlK9nTiyTZKAyj18OTWDPGV6rjeWc_GvKn0W5N_YWHKFD_Tswzn1pfBAWGUiwfnIf504u8CxCxklmVeY2W6xXV5lwQUR5bEs8-1LSB_LF5znaRu0uLNOIdIQPTx1VoeTVWZfPqa0Ene-2Cnp)
3. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGs-Q8i69Yg8Om64CnIZECYBVD04ZtV-G6KBsedxbHppiy8oeH5pGJlZd3sGdGyWKt0cS7R4YDAEhbHYtuqrdQNH1xpsL_Azq3WGO2Ulo5gKSCZuPE_sXxR4ZD6nMVqqHP-SUutHqaoItFNMQqShwkWRrRWWyGmoXoe2gfShFzrJyTEUQ-K28OWTtwexb9d)
4. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGRiLCZJBtzb-vaCGoRNtIUz4r-JvgB92oKu85c20ogziE5nmoA7SAgqStIqTfRqGbSHHLTU9wYiV4qMO-dgVJiVIPtFdzvrQ3ue6TLuJ4o5QWCIwPW3NCrylGcCgIoEpMbUeU9cpSmoFybqd1H6mU3xGiCQaQS0NEMpX0kVUm2UoTQnEX96wlHf7cMBhbHKrQHP_a73sblUl5nS8DAgtI=)
5. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGIn9d7Ca4c30sAlqKDxh1JTMWHzvvXAyWpbY5qyHFif35PcXDHtfEvD-IDnFp-QHTg-0olNHpRcoPJ1l4DiejmIzxAuw42ZxItCD6mt7eTkdP9kV3CdjqPHuG1sFxdRQ==)
6. [apache.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGHrgwEBmE_LRRhTpeD8pe0L9EHyNENRVhHk_gzO1NT5HAIMacBUeDLAtYCyDnBhIe8BujrylwCNU9UAS49oY0tyixDlm2q5gnyxZA5Q1a7PJe6yotvvvE=)
7. [apache.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHTKFyrfotWum1CrBMx3i34Qk7XJbKtoyUSkn1F4wncFg49Sdt7PWNm0cx3Gfuik3ldMcz_QuN6dL3dHbyUjChGkkKleo3DWezNTxGsShBXMtpMwdhRuVjEkG5q__uCV2taxTbscys=)
8. [sonatype.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEcTzAkg2JlPzL4pbM7MKxMBybUYuDFpYq8pqBYOEeAqFnTBM_EuQg1FZikrXRerdd_4rnSnhsMRPKCphc1yTVGp6SZSfNg8r3KrP_ggs7daPAcSL2YhwEzkZHVrcor-9rk_kh9U5Rf4QM=)
9. [sonatype.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHr9ob87aMlXkTJAOJnKegUF-18PObo-c0-TEJu_Bauzhb-OVpNohcQb5W-nTn3ONd9yqhzj4IBpYD5dNV4ury8pImqc30EY-x24G4vE5EoGnvA5HIkFEzNVUQET2PWKT9EWfyqiz6ZYRgwJeg1QLEZfBdMpHMjT37GI_9GwH2hwv3zj0_Ajn1hLQ==)
10. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHaen2jXwhXem4tPC6WotYOlJgmdYa_d51ochBbTFynCqNM54-XsZy0rzxkVR8hhV6YlRwwjm3XNbV0tfBSOKIAQoEGOOaItl-o47v5A78QTE5yRfUBsx9A4cyCpU3JiB-wKI0cHXXn14R10IxGzje3iAwjBnBAF0FDy3RU1ai30W_Q118legYD3Ca7N7kh-X3xO1eSXyPRzbdo08G_)
11. [apache.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG6jad62mT49ntCtMcMcHNeaq6QrCLKnRZLDmsicRRTBkxw8j0J__zg_cXOlXD2dtnzk3OKqAv_3qlRRYJMnGD449YOwZ-FDV0_nHSBbffACZUkYWFbuioGbkSlMKVOcltnIzzakAO05ulKqvAPCpiugXYMqC8DPog=)
12. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF0poFNZyjLRYxSClqmOU4W7XocLgzMN-EeHr3AkUKqrOl6iXlf_kQeTmI9inxfOkgVNzKjw2aYyJubmsDZVJu015lknsRAHobzNIwDmQ-gf0aUEw==)
