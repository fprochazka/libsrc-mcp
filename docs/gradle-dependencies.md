# Comprehensive Guide to Extracting and resolving Gradle Dependency Trees

## Executive Summary
Extracting a complete, machine-readable dependency tree from Gradle projects presents unique challenges compared to declarative package managers (like npm or Maven) because Gradle build scripts are executable code (Groovy or Kotlin DSL). There is no built-in native JSON output for the dependency tree, requiring developers to rely on custom tasks or the Tooling API for robust extraction. 

The standard `gradle dependencies` command provides a human-readable text visualization but is difficult to parse programmatically due to its formatting of omitted subtrees `(*)` and constraints `(c)`. For accurate programmatic analysis, the `ResolutionResult` API within a custom task is the most reliable method. When Gradle cannot be executed, static analysis of `libs.versions.toml` (Version Catalogs) offers a partial view, though it lacks the context of the resolved graph. Mapping resolved artifacts to source code repositories relies on inspecting the `<scm>` tag in the resolved POM files or utilizing third-party aggregation APIs like `deps.dev`.

---

## 1. The Standard CLI Approach: `gradle dependencies`

The primary built-in mechanism for inspecting dependencies is the `dependencies` task. While designed for human readability, it is often the first target for scraping tools.

### 1.1 Command-Line Invocation and Filtering
To run the task, use the Gradle wrapper script (`gradlew`). This ensures the exact Gradle version defined for the project is used.

**Basic Invocation:**
```bash
./gradlew dependencies
```

**Filtering by Configuration:**
Gradle projects contain multiple "configurations" (buckets of dependencies). The most relevant for dependency analysis in Java/Android projects are:
*   `compileClasspath`: Dependencies required to compile the source code.
*   `runtimeClasspath`: Dependencies required to run the application (includes transitive dependencies not needed for compilation).
*   `testCompileClasspath`: Dependencies for compiling tests.

To extract a specific tree, use the `--configuration` flag [cite: 1, 2]:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

### 1.2 Output Format Analysis
The output is a tree-like text structure. Understanding specific markers is critical for parsing:

*   **Tree Structure:** Uses `+---` and `\---` to denote branches and leaf nodes [cite: 3].
*   **Version Conflict Resolution (`->`):** Indicates that the requested version was overridden.
    *   Example: `com.google.guava:guava:19.0 -> 23.0` means 19.0 was requested, but 23.0 was selected (usually due to conflict resolution or constraints).
*   **Omitted Subtrees `(*)`:** Indicates that this dependency subtree has already been displayed elsewhere in the output. Gradle omits duplicates to keep the output concise [cite: 2, 4].
    *   *Parsing Implication:* A parser must maintain a map of seen subtrees to reconstruct the full graph.
*   **Constraints `(c)`:** Indicates the entry is a dependency constraint (often from a BOM/Platform) rather than a direct artifact dependency [cite: 2, 5].
*   **Not Resolved `(n)`:** The dependency could not be resolved or the configuration is not meant to be resolved [cite: 2].

**Example Output:**
```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- org.springframework.boot:spring-boot-starter-web:2.5.4
|    +--- org.springframework.boot:spring-boot-starter:2.5.4
|    |    +--- org.springframework.boot:spring-boot:2.5.4
|    |    |    \--- org.springframework:spring-core:5.3.9
|    |    |         \--- org.springframework:spring-jcl:5.3.9
|    |    \--- org.springframework.boot:spring-boot-starter-logging:2.5.4 (*)
```

---

## 2. Programmatic Extraction (JSON Workarounds)

Since Gradle does not natively support JSON output for the `dependencies` task [cite: 6], relying on text parsing is brittle. The following methods are recommended for robust tool building.

### 2.1 Custom Task using `ResolutionResult` (Recommended)
The most accurate way to get a full graph is to query Gradle's internal resolution engine using the `ResolutionResult` API [cite: 7, 8]. This API provides access to the resolved graph, selection reasons, and variant details.

**Implementation Strategy:**
Create a custom task in the build script (or inject it via an init script) that traverses the root of the `runtimeClasspath` configuration.

**Groovy Custom Task Example:**
```groovy
// Add to build.gradle or init.gradle
task printDependenciesJson {
    doLast {
        def config = project.configurations.findByName("runtimeClasspath")
        if (!config) return
        
        // Force resolution
        def result = config.incoming.resolutionResult
        def root = result.root

        def traverse
        traverse = { node, seen ->
            def id = node.id.displayName
            if (seen.contains(id)) return [id: id, status: "duplicate"]
            seen.add(id)
            
            [
                group: node.moduleVersion?.group,
                name: node.moduleVersion?.name,
                version: node.moduleVersion?.version,
                details: id,
                reason: node.selectionReason.descriptions.collect { it.description },
                children: node.dependencies.collect { dep ->
                    if (dep instanceof org.gradle.api.artifacts.result.ResolvedDependencyResult) {
                        return traverse(dep.selected, new HashSet(seen))
                    } else {
                        return [requested: dep.requested.displayName, status: "unresolved"]
                    }
                }
            ]
        }
        
        def json = new groovy.json.JsonBuilder(traverse(root, new HashSet())).toPrettyString()
        new File(project.buildDir, "dependency-tree.json").text = json
        println "Dependency tree written to build/dependency-tree.json"
    }
}
```

### 2.2 Gradle Tooling API
For external tools (like IDEs or CI scanners) that cannot modify the `build.gradle` file, the **Gradle Tooling API** is the standard approach [cite: 9]. It allows you to embed Gradle execution within a Java/Kotlin application.

*   **Advantage:** Does not require modifying target source code.
*   **Implementation:** Use `GradleConnector` to connect to the project and request the `EclipseProject` or `IdeaProject` model, or run the custom task defined in 2.1 via an init script injection.

### 2.3 Why Not `resolvedConfiguration`?
Older scripts use `configuration.resolvedConfiguration.firstLevelModuleDependencies`. This is now considered legacy. The `incoming.resolutionResult` (introduced in Gradle 1.2+) is superior because it correctly models the dependency graph (including cycles and constraints) rather than just a flattened artifact list [cite: 7].

---

## 3. Handling Multi-Module Projects

In a multi-module build, running `gradle dependencies` at the root often only shows the root project's dependencies (which may be empty).

### 3.1 Iterating Subprojects
To get the tree for all modules, you must apply the logic to every subproject.

**CLI Approach:**
You can iterate using `gradle dependencies` on specific subprojects, but getting them all in one go requires a loop or a custom script [cite: 10, 11].
```bash
# Runs dependencies task for every subproject
./gradlew allprojects:dependencies
```

**Custom Task Approach:**
In the custom task strategy (Section 2.1), wrap the logic in an `allprojects` block within the root `build.gradle` or an init script.

```groovy
allprojects {
    task printDeps {
        doLast {
            // ... extraction logic here ...
        }
    }
}
```

---

## 4. Gradle Version Catalogs (`libs.versions.toml`)

Introduced in Gradle 7.0 (stable in 7.4), Version Catalogs allow centralized dependency management. This file is usually located at `gradle/libs.versions.toml` [cite: 12, 13].

### 4.1 TOML Structure
The file has four sections:
1.  **`[versions]`**: Defines version variables.
2.  **`[libraries]`**: Defines dependency coordinates (Group:Artifact:Version).
3.  **`[bundles]`**: Groups libraries (e.g., `retrofit-bundle` includes retrofit and gson-converter).
4.  **`[plugins]`**: Defines plugin coordinates.

**Example `libs.versions.toml`:**
```toml
[versions]
retrofit = "2.9.0"
okhttp = "4.9.0"

[libraries]
retrofit = { module = "com.squareup.retrofit2:retrofit", version.ref = "retrofit" }
okhttp-logging = { group = "com.squareup.okhttp3", name = "logging-interceptor", version.ref = "okhttp" }

[bundles]
networking = ["retrofit", "okhttp-logging"]
```

### 4.2 Static Parsing Strategy
Since `libs.versions.toml` is a static configuration file, it can be parsed without running Gradle.
1.  **Parser:** Use a TOML parser (e.g., `tomli` for Python, `jackson-dataformat-toml` for Java).
2.  **Resolution Logic:**
    *   Read the `[libraries]` section.
    *   If a library uses `version.ref`, look up the value in `[versions]`.
    *   Construct the coordinate: `group:name:version`.
3.  **Limitations:** This only provides *declared* dependencies. It does **not** provide the resolved tree, transitive dependencies, or conflict resolution. It is useful for inventory but not for a full SBOM.

---

## 5. Execution Context: Wrapper vs. System Gradle

### 5.1 Gradle Wrapper (`gradlew`)
Always prioritize using `./gradlew`. The wrapper locks the project to a specific Gradle version (defined in `gradle/wrapper/gradle-wrapper.properties`), ensuring compatibility with the build script DSL [cite: 14]. Using a system-installed `gradle` may fail if the version differs (e.g., building a Gradle 4.x project with Gradle 8.x).

### 5.2 Handling Environments without Gradle
If Gradle is not installed and cannot be run (e.g., simple static analysis):

1.  **Parse `libs.versions.toml`:** As described in Section 4.
2.  **Parse `build.gradle` / `build.gradle.kts`:**
    *   **Regex/Text:** Search for patterns like `implementation "com.example:lib:1.0"`. This is highly unreliable due to variables (`implementation "com.example:lib:$ver"`), loops, and conditional logic [cite: 6, 15].
    *   **AST Parsing:** Use a library like `kotlin-compiler-embeddable` to parse Kotlin DSL or a Groovy parser for Groovy DSL. This is complex but more accurate than Regex.
    *   **Conclusion:** Static analysis of build scripts is an approximation. Accurate resolution requires executing the build tool.

---

## 6. Gradle Platforms and BOMs

Gradle Platforms (Bills of Materials) complicate dependency trees. They do not contain artifacts but define constraints (suggested or enforced versions) [cite: 16, 17].

### 6.1 Impact on Resolution
*   **Recommendation:** `implementation platform('com.example:bom:1.0')` sets a "soft" version.
*   **Enforcement:** `implementation enforcedPlatform(...)` sets a hard constraint, overriding other versions.
*   **Output:** In the dependency tree, BOMs appear with `(c)`. Artifacts controlled by a BOM may not show a version in the build script but will appear resolved in the tree.

**Handling in Tools:** When parsing the tree, treat `(c)` nodes as metadata sources that influence the versions of other nodes, rather than executable code artifacts.

---

## 7. Data Availability in Output

When using the `ResolutionResult` API (Section 2.1), the following data is available [cite: 8, 18]:

| Data Point | Description | API Accessor |
| :--- | :--- | :--- |
| **GAV** | Group, Artifact, Version | `moduleVersion.group`, `name`, `version` |
| **Selection Reason** | Why this version? (Requested, Forced, Conflict Resolution) | `selectionReason` |
| **Requested Version** | What the build script asked for vs what was resolved | `requested.displayName` vs `selected.id` |
| **Dependents** | Who requested this library? (Reverse graph) | `dependents` |
| **File Path** | Location of the JAR on disk | `artifact.file` (Requires resolving artifacts) |

---

## 8. Debugging with `dependencyInsight`

To investigate why a specific library version was chosen or to find where it comes from, use `dependencyInsight` [cite: 2].

**Command:**
```bash
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
```
*   **--dependency:** Matches part of the group or name.
*   **--configuration:** Mandatory (defaults to `compileClasspath` in some versions, safest to specify).

This command returns a "path to root" view, showing exactly which libraries requested the artifact and how conflicts were resolved.

---

## 9. Finding Project Repositories

To determine where Gradle downloads dependencies from, you must inspect the `repositories` block.

**Custom Task for Repository Extraction:**
Repositories can be declared in `build.gradle` or `settings.gradle` (in `dependencyResolutionManagement`).
```groovy
task listRepos {
    doLast {
        println "Repositories:"
        project.repositories.each { repo ->
            if (repo instanceof MavenArtifactRepository) {
                println "Name: ${repo.name}, URL: ${repo.url}"
            }
        }
    }
}
```
This outputs the URLs (e.g., Maven Central, JCenter, internal Artifactory) [cite: 19].

---

## 10. Mapping Artifacts to Source Code Repositories

Gradle resolves binaries (JARs), not source code. Mapping a resolved binary (e.g., `com.squareup.retrofit2:retrofit:2.9.0`) to its GitHub repository requires external data.

### 10.1 The Maven/Gradle POM Standard
Gradle uses the same metadata format as Maven. Every resolved artifact has a `.pom` file.
1.  **Resolution:** Resolve the dependency artifact.
2.  **Inspection:** Read the `<scm>` section of the POM file.
    ```xml
    <scm>
      <url>https://github.com/square/retrofit</url>
      <connection>scm:git:git://github.com/square/retrofit.git</connection>
    </scm>
    ```
3.  **Limitation:** This field is optional and often missing or inaccurate in older internal libraries.

### 10.2 Using `deps.dev` API
For open-source packages, the `deps.dev` API (by Google) provides aggregated metadata, including source repositories [cite: 20, 21].

**API Usage:**
*   **Endpoint:** `GET https://api.deps.dev/v3alpha/systems/maven/packages/{group}:{name}/versions/{version}`
*   **Response:** JSON containing the `links` field with source code URLs derived from different registries.

### 10.3 Summary Strategy for Tooling
To build a tool that resolves dependencies and finds source code:
1.  **Execute Gradle:** Use a custom init-script with `ResolutionResult` to dump the resolved dependency graph to JSON.
2.  **Extract Repos:** Use the repository extraction task to know where artifacts came from.
3.  **Resolve Source:**
    *   *Step A:* Attempt to download the POM for each artifact from the identified repository and parse `<scm>`.
    *   *Step B:* If Step A fails or is empty, query the `deps.dev` API using the Group:Artifact:Version coordinates.

**Sources:**
1. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEpwxzLr5pr5U2Rxg5tx416Eyd0yebFzYfTrvf_TP_uq2CEaMCBoH4srWN-93RZlXvkaihDGzQJ0FLkYWbPgQtZl-e_brUoWggly7doIzi2TMwk__2ySdRSjHQFgDuSfeRxRC666mKT-ADNU-62Eo0E0DY1uFAOk9Ccr0I=)
2. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHAZIPy3X8ekC3XEqRtDcwjJwv-wK4Py9vuIQTtaN-rwJDpaNnfAcDjVl6_l_UfIt-MiFdWUka3mOahwY9AX56rH-T157U_s2xVw2BmWpE-nOF5BzURhg_GVglYeqPutMh9WJnxV3WFOkX3ZgmoE29nSS4YM4qkauOANI_ox8b_6EpaIQ==)
3. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFBZDoosgYBuzJOyAR_U3V4ROfhNOjYeBCy2SSaLi-H7jADNBqMBUHXWVR4Vqr4AOj77f8livxbUZpVegiruMxKBTSiaN8TmkOAAhp409J9wdT-oXZSDKnnOUqVUVpN1gSTRAUpP4bNtzya0JsBsbLkCyCDIoi_8qoNayHK2Dpop6VjA9TbbevR5yYZGhU=)
4. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG6vhWIYFocpILdQwyO6frt3B7_ugawCyxe9nQxV_tLrrzpl7OAhy14ed5vDoiP9zTi67SroeFEi1RVWj_PHwzIw4iCPym8FLVKhRCpuBuVvK8UnUGY6bFogz-cbKA1yWHmADzCMRobPZEAD8uhQy621U9mhodHp7kyk1yvJocx6NoiD2_RGcQDc3cR)
5. [dzone.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEqZvCXIvj46RVuRpinuajjcakS7bKLXmEt8Mu3CBuHsjubmX6oQszgmuQ0RkVHAVnD1tqIbx-_Q7LtF2H7daee4aOXg1-IERAsBbb6vq73JCIqGaNJve34X0waOSSkQHt9zFIGMlGscA3nLu5FeG6T8okveKnm_c5ym9q11Upw9S4LVg==)
6. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGyD4kEH5akOuYB2FjjutFV_v27GpFFV7gCfsD1VhuRc9i9-YXyF1ghtnUiIhAXO-sIAhZ951ozLnEKISzpONk4PmcGDLavxLkdlGYnSC_VLLMNbmjf1wKdEVXB5vtmwe1R4TM=)
7. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQECPlniz5nSjDKjCePqv8TPncyPISrwcBe1miGQEOE0c5QpdTOg4SZgBHAQOvfkz6tu20sVK8zbRbMWb0G5FgGEXnsIIGNE37rFs9l19YdFzg8hExoO_0zEPLu_SXdHSfG9c99AyHC1MAu5oq86PTcjuM-l4g-9gbT-zJ6V2NJ4br2uHKjTjoq27WqlnHBB3S5x8LQqpO5z1BMtuca2C1FSvBgp6waiTMF-oTe5yg==)
8. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGQZX5CwT4eTA9_8MrH9tiLljpdOoRjjJDJ1o6I9bUl1TKLK0HtNxpaMSpANOLmQGJbd_jhZuPLT11IODfihOW2VjFeMO0k4UDm0BtCOkXIBMizlyWkxaKO08EZagSg6gdfLXBw39pv0T_SeKBcEnvJOZS_TDdFbYA4ri4Gv5n4fpS6-Cpr1HT2PZBMjNDS79vxOYk=)
9. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH8jcIDdN3qGbRCBw7wI5iMTJu7WtoF8FFrvqPLqoF3VwPf_w_6JN1uutbWJ5mlT0R1fYhcmNixFSeGr2J7rEler_xh0qYDntEvRnUUJCWqtTpe0g8s7b_H5Hpfjp0mHvdSDlNCe7_SFfekL2olLVUC)
10. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGMW_3ZDhjBHYt5Qz9dDEe3RVsmVBxNuaT2m8VFL3iBv9HU_geKap7CvUSD9imSY_SdLsZhHbAZymqyAB25wk1_7UyprG3Y4bHgW0ZAzRLIP-bjzPIXd8ZhgnihaB5q0haaD31UGQi5-nUHt9YDlDXFtZyPufLFiYSdtZq48N0w05uAgi2w8bA_G9lZFllHcsf26jzV50geGJVHx-wr5ws9GZ7MzQ==)
11. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG11Xq4N3mtsoHseoUdgqkezt3sPURtP1VFEvsFxpgaeD1FClliywS28rwb_vw1ngVfnD94pXUFt2_ydYAp2uyMQ8t08MLt776rE5AUeLoZq2AzGtunDuzT8zPUkLXzVCS83EDktxoeVwkLzfPIOehxSde_zON890QYToKroHJb6UZT4lGPC1e38M7StliPpw==)
12. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHTdyKyDHZFBYTOMsFc8KgHLRCPGqtpr2xywaLM-7hgjVO7a_HIqzRKM-BiXq5aJp457koNOx8dSEK8iySKk6k3IA0SpR8gCMSDCHhGfSv8jlbtpZmDwfUXMcsqW7sxaVr4izacb5XExi6EHEGELfky8l7P50Y=)
13. [android.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGV9M3cNrRMm-lGos_2B010sqHQBTAAyjpTEM_6qERlX7WoqyhKGWJYqBGOmNpOPHKeqlHs34fhi91Hpv9YJ_0V5vIzSh-SmLrB2u1gHP3QGXGZy7xLcOXAOKt9OU3qeNG1zBPgu-qYUD_zp9wG)
14. [odu.edu](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFwEvR11CdL3hT1YxPNH3CwAAr4UQUxvZhlNKHLTIvyJz_FNsqOhhhHEBslY2TmprGTwg07e9iLKoH2An8_fZJEC834DPcEtjqN3hoCwXGiEa-y5eiHiXhfXqbRFIwWBkkf6ruetMbwAHui0zuRzcwLYk02KYw=)
15. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFhYWpl5-FseCRFPV2BMXdzR-47f9LmiSUw5CQBRyVwgQ-lcAHHzCZ8G7ZD3BdqgHF8Tz9-68FnPuUMpm1Kkckls8WkuHalrYD24tObsz_ANkNSMbrtUuXOt41bmJRf7MwAyb6o26awFTW-J2Y1gh6g1azmSbEZwVw6UuqS2-Olw_b-npYwJlTt)
16. [dzone.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHGqAtR5GhJ7tp9jE6dlOWfWs62p9XiLyubpYu2vqBETdR5HLs4BYPXUMYM2jxGmusLAWZs844t7D4sYS4617Nl6Lf1AnWs98rsLamM3-AgCL__NEeFFIvIUKz3B5z00TzxJQmLlIIwR6RBJevcYJKRVeuowGbmJaj-u83Ppyo0BfzJZA==)
17. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHAAvbyCeY751P71e6_jRPBV_6DhkO2VYyYzi8IDpo613MqW77S8TVK-5FcXRSD-v94VxvMHSfV8vKoMv3se1azs2K-YiTzm-0NLV5uycmNjgsKtUW9RGzAklUIDYXE57Jspg3qmUZdgBJsf_Mucg==)
18. [gradle.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEdi-PbtVKbc2L8wEyWk1wqNnQ_lM2Tlw_uIJz_CVhSJ24ERQtrGSdz0EJi9y1_wGkpHN_dByHJJ7mMOarnbDOdhOlOTxK5-Pk5JNr9lzSiWGfpYewDDRFLBeTNjbha9I9zBGaWZ46BTYw4f8w93o3WcsIrMoU1Axo_VlENdHCdt87zBQfd0tbN2I5cGf_PUFZsgz86WKevb4Z_SQ==)
19. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFyeTB9tqQVKjke8H1K6dHhy30Qt8zeIyLv7C_tynffpzmeOlkkj2jGfAXiRr0NOu4A04Esp3AWeoIBRudh4egsukAkhDsjpH8en5PdPGKD4fl8u36I9eylY9nxxHqgUPKcc5Fuf01X7z3qMO8P5Pon_ZkIFWd69ufabF4rhLR3ubOtA8rXeTu1M8I=)
20. [deps.dev](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEp2ZQyYukBrX9CU6Dg8O4E46J_97pwPGsjkOzREfTM68GNlL7lwtiO5IKcI5RwsatDt8xUG7N1p6wiIaseu47P4WLomqaH8ETsUKlXNyZ6MHZu4w==)
21. [googleblog.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGnRX8UgY8db819yfzCh9pnnd9FCrxGPER9fJbOBRuWQQTdsqfZ6d6CO_Y9bdvr5DDI-RfWMYL_kOrOkxFAerztc8OFIckzi2VBd0ShasuXOu5UdiEoScuU3lPDfjPL9yYQ5CY7-uXs3T1S0aqbkjsZ5qUqhHuX7FRWcSz2dHX-JtKi)
