plugins {
    id("com.android.application")
}

android {
    namespace = "com.kartik.mcqueencontroller"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.kartik.mcqueencontroller"
        minSdk = 26
        targetSdk = 36
        versionCode = 8
        versionName = "8.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}
