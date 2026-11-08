from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from crawler import Crawler
from .models import URLSubmission


@admin.register(URLSubmission)
class URLSubmissionAdmin(admin.ModelAdmin):
    list_display = ("url", "priority", "status_badge", "indexed_pages", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("url",)
    list_editable = ("priority",)
    readonly_fields = ("status", "indexed_pages", "last_error", "created_at", "updated_at")
    actions = ("queue_for_recrawl",)
    fields = ("url", "priority", "status", "indexed_pages", "last_error", "created_at", "updated_at")

    @admin.display(description="Status")
    def status_badge(self, obj):
        return obj.get_status_display()

    def save_model(self, request, obj, form, change):
        normalized = Crawler._normalize(obj.url.strip())
        host = Crawler._normalize(normalized or "")
        if not normalized or not host:
            raise ValidationError("Enter a valid HTTP(S) URL without credentials.")
        if not 1 <= obj.priority <= 100:
            raise ValidationError("Priority must be between 1 and 100.")
        obj.url = normalized
        if not change:
            obj.status = "pending"
        else:
            obj.status = "pending"
            obj.last_error = ""
        super().save_model(request, obj, form, change)

    @admin.action(description="Queue selected URLs for indexing")
    def queue_for_recrawl(self, request, queryset):
        count = queryset.update(status="pending", last_error="")
        self.message_user(request, f"Queued {count} URL(s). The queue worker will crawl them if robots.txt permits.", messages.SUCCESS)
