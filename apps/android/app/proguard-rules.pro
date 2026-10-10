# kotlinx.serialization keeps its generated serializers through reflection-free lookups.
-keepclassmembers class com.example.inbox.** { *** Companion; }
-keepclasseswithmembers class com.example.inbox.** { kotlinx.serialization.KSerializer serializer(...); }
