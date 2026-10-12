import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Every identity value comes from the brand file; nothing is written into this
// script, so a value here can never silently pin the example identity.
val brand = Properties().also { properties ->
    rootProject.file("brand/brand.properties").inputStream().use { properties.load(it) }
}
fun brand(key: String): String = brand.getProperty(key, "").trim()
fun brandField(key: String): String = "\"" + brand(key).replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "com.example.inbox"
    compileSdk = 36

    defaultConfig {
        applicationId = brand("BRAND_APPLICATION_ID")
        minSdk = 26
        targetSdk = 36
        versionName = brand("MARKETING_VERSION")
        versionCode = brand("CURRENT_PROJECT_VERSION").toIntOrNull() ?: 1
        resValue("string", "app_name", brand("BRAND_PRODUCT_NAME"))
        manifestPlaceholders["urlScheme"] = brand("BRAND_URL_SCHEME")
        listOf(
            "BRAND_PRODUCT_NAME", "BRAND_PRIMARY_COLOR", "BRAND_DEFAULT_SERVER", "BRAND_HOSTED_LABEL",
            "BRAND_HOSTED_SERVER_TEMPLATE", "BRAND_HOSTED_SIGN_IN", "BRAND_PRIVACY_POLICY_URL_EN",
            "BRAND_PRIVACY_POLICY_URL_ES", "BRAND_SUPPORT_URL_EN", "BRAND_SUPPORT_URL_ES",
            "BRAND_FCM_PROJECT_ID", "BRAND_FCM_APP_ID", "BRAND_FCM_API_KEY", "BRAND_FCM_SENDER_ID",
        ).forEach { key -> buildConfigField("String", key, brandField(key)) }
        buildConfigField("String", "BUILD_STAMP", "\"" + ZonedDateTime.now(ZoneOffset.UTC).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")) + " UTC\"")
    }

    // The upload key lives outside the repository. It is read from Gradle properties
    // (uploadKey.*) or the environment (UPLOAD_KEY_*); without it a release build is
    // left unsigned.
    val signing = listOf("STORE_FILE", "STORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD").associateWith { key ->
        (project.findProperty("uploadKey.$key") as String?) ?: System.getenv("UPLOAD_KEY_$key") ?: ""
    }
    if (signing.values.all { it.isNotBlank() }) {
        signingConfigs {
            create("upload") {
                storeFile = file(signing.getValue("STORE_FILE"))
                storePassword = signing.getValue("STORE_PASSWORD")
                keyAlias = signing.getValue("KEY_ALIAS")
                keyPassword = signing.getValue("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (signing.values.all { it.isNotBlank() }) signingConfig = signingConfigs.getByName("upload")
        }
    }

    sourceSets {
        // The icon set and logo sit beside the brand file, so a publisher replaces one directory.
        getByName("main").res.srcDir(rootProject.file("brand/res"))
    }

    buildFeatures {
        compose = true
        buildConfig = true
        resValues = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.06.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha07")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    // The platform's push channel, initialised at runtime from the brand file; no config plugin.
    implementation("com.google.firebase:firebase-messaging:24.1.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
}
