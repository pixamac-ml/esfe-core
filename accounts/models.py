from django.db import models
from django.contrib.auth import get_user_model
from django.templatetags.static import static

User = get_user_model()


def profile_upload_path(instance, filename):
    return f"profiles/{instance.user.id}/{filename}"


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    avatar = models.ImageField(
        upload_to=profile_upload_path,
        blank=True,
        null=True
    )

    bio = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user.username}"

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return static("images/default-avatar.png")