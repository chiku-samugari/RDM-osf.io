from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.UserList.as_view(), name='user-list'),
    url(r'^(?P<pk>\w+)/$', views.UserDetail.as_view(), name='user-detail'),
]
