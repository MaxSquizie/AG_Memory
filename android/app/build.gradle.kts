import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

val repoRoot = rootProject.projectDir.parentFile
val localProperties = Properties()
val localFile = rootProject.file("local.properties")
if (localFile.exists()) {
    localFile.inputStream().use { localProperties.load(it) }
}

val generatedPython = layout.buildDirectory.dir("generated/python")
val generatedAssets = layout.buildDirectory.dir("generated/ahAssets")
val stalePythonDir = project.file("src/main/python/ah")
val staleRagDirs = listOf(
    project.file("src/main/python/rag"),
    generatedPython.map { it.dir("rag") },
)

val removeStalePython by tasks.registering(Delete::class) {
    delete(stalePythonDir)
    delete(staleRagDirs)
}

val embedAhPython by tasks.registering(Copy::class) {
    dependsOn(removeStalePython)
    from(repoRoot.resolve("src/ah")) {
        into("ah")
        exclude("**/__pycache__/**")
        exclude("gui/**")
        exclude("llm/embeddings.py")
        exclude("diagnostics/m4_acceptance.py")
    }
    from(project.file("src/main/python")) {
        include("*.py")
        exclude("ah/**")
        exclude("rag/**")
    }
    into(generatedPython)
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
}

val embedAhAssets by tasks.registering(Copy::class) {
    into(generatedAssets.map { it.dir("ah") })
    from(repoRoot.resolve("config/android.toml")) {
        into("config")
    }
    from(repoRoot.resolve("prompts")) {
        into("prompts")
    }
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
}

val tensorDispatchSo = project.file("src/main/jniLibs/arm64-v8a/libLiteRtDispatch_GoogleTensor.so")
val tensorCompilerPluginSo = project.file("src/main/jniLibs/arm64-v8a/libLiteRtCompilerPlugin_google_tensor.so")
val checkTensorDispatchSo by tasks.registering {
    doLast {
        check(tensorDispatchSo.isFile && tensorDispatchSo.length() > 100_000) {
            "Need LiteRT v2.2.0 Tensor dispatch at $tensorDispatchSo " +
                "(from litert_npu_runtime_libraries_jit.zip on the LiteRT v2.2.0 GitHub release)."
        }
        check(tensorCompilerPluginSo.isFile && tensorCompilerPluginSo.length() > 100_000) {
            "Need LiteRT v2.2.0 Tensor compiler plugin at $tensorCompilerPluginSo."
        }
    }
}

afterEvaluate {
    tasks.matching { task ->
        val n = task.name
        n != "embedAhPython" && n != "embedAhAssets" && n != "removeStalePython" && (
            n == "preBuild" ||
            (n.startsWith("merge") && n.endsWith("Assets")) ||
            n.contains("PythonSources") ||
            n.contains("PythonRequirements")
        )
    }.configureEach {
        dependsOn(removeStalePython, embedAhPython, embedAhAssets, checkTensorDispatchSo)
    }
}

android {
    namespace = "com.ahmemory.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.ahmemory.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        jniLibs {
            // Extract .so on install so Backend.NPU(nativeLibraryDir) can dlopen
            // libLiteRtDispatch_GoogleTensor.so next to liblitertlm_jni.so.
            useLegacyPackaging = true
        }
    }

    buildFeatures {
        compose = true
    }

    sourceSets.getByName("main") {
        assets.srcDir(generatedAssets)
        withGroovyBuilder {
            "python" {
                invokeMethod("setSrcDirs", listOf(generatedPython.get().asFile))
            }
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            install("pymorphy3>=2.0.6,<3")
            install("pymorphy3-dicts-ru")
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.11.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.16.1")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
