from django.conf import settings
from django.conf.urls.static import static
from .urls_staging import urlpatterns
urlpatterns = [*urlpatterns, *static('/media/', document_root=settings.MEDIA_ROOT)]
