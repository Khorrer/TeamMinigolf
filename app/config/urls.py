from django.contrib import admin
from django.urls import include, path

# Diese beiden neuen Zeilen hinzufügen
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# Dieser Block erlaubt Django, die CSS-Dateien während der Entwicklung auszuliefern
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
