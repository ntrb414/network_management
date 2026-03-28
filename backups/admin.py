from django.contrib import admin
from .models import ConfigBackup


@admin.register(ConfigBackup)
class ConfigBackupAdmin(admin.ModelAdmin):
    list_display = ('id', 'device', 'version', 'status', 'backed_up_at', 'backed_up_by')
    list_filter = ('status', 'backed_up_at')
    search_fields = ('device__name', 'commit_message', 'git_commit_hash')
    readonly_fields = ('git_commit_hash', 'backed_up_at')
    ordering = ('-backed_up_at',)

    def version(self, obj):
        return obj.version
    version.short_description = '版本'
