plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.20" apply false
    id("com.chaquo.python") version "16.1.0" apply false
}

fun localBuildDir(projectName: String): java.io.File {
    val base = System.getenv("LOCALAPPDATA")
        ?: "${System.getProperty("user.home")}/.cache"
    return java.io.File(base, "AHMemory/android-build/$projectName")
}

layout.buildDirectory.set(localBuildDir(rootProject.name))
subprojects {
    layout.buildDirectory.set(localBuildDir(project.name))
}
