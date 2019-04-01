from django.urls import path

from . import views

app_name = 'dpq'

urlpatterns = [
    path('', views.index, name='index'),
    path('stats', views.stats, name='stats'),
    path('jobs', views.jobs, name='jobs'),
    path('workers', views.workers, name='workers'),
]
