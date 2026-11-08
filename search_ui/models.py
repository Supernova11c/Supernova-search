from django.db import models


class URLSubmission(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("complete", "Complete"),
        ("no_pages", "No pages indexed"),
        ("failed", "Failed"),
    ]

    url = models.URLField(max_length=2048, unique=True)
    priority = models.PositiveSmallIntegerField(default=75, help_text="Editorial ranking boost from 1 to 100.")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    indexed_pages = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "URL injection"
        verbose_name_plural = "URL injections"

    def __str__(self):
        return f"{self.url} (priority {self.priority})"
