from django.contrib import admin

from .models import ConstructionLocation, ConstructionParticipant, ConstructionProject, ConstructionProjectMember


@admin.register(ConstructionProject)
class ConstructionProjectAdmin(admin.ModelAdmin):
    list_display = ("project_number", "name", "organization", "status", "progress_percentage")
    list_filter = ("status", "organization")
    search_fields = ("project_number", "name", "client_name")


admin.site.register(ConstructionParticipant)
admin.site.register(ConstructionProjectMember)
admin.site.register(ConstructionLocation)
